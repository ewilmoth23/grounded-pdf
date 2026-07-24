"""Claim-level verification of persisted assistant answers.

Verification is a read-only lens over an already persisted answer: it splits the
answer into sentences with a deterministic rule-based splitter (no model), embeds
each sentence, and scores it against the evidence available to the conversation.
It never mutates the message, its citations, or any retrieval state.

Caching: results are held in a small in-process LRU. Messages are immutable
once persisted, but verdicts also depend on the evidence scope and thresholds,
so the key combines the message id with the scoped document ids, their latest
``updated_at``, and both verdict thresholds. The cache is additionally cleared
when documents are deleted or reprocessed and when runtime settings change. A
database column was deliberately avoided because verification is a derived,
recomputable artifact and adding schema for it would be churn without benefit.
"""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.entities import ConversationDocument, Document, Message, utc_now
from app.rag.chat import COMPARE_MODE, validate_matches
from app.rag.grounding import (
    CITATION_MARKER_RE,
    GENERATION_FAILED_MESSAGE,
    INSUFFICIENT_EVIDENCE,
)
from app.rag.retrieval import content_tokens
from app.services.embeddings import EmbeddingProvider
from app.services.vector_store import VectorMatch, VectorStore

Verdict = Literal["supported", "weak", "unsupported"]

_CANDIDATES_PER_SENTENCE = 5
_EXCERPT_LIMIT = 320
_CACHE_LIMIT = 128

# Dotted tokens that end sentences without ending the sentence. "p"/"pp" also
# protect the page part of citation markers ("[name, p. 2]") from splitting.
_ABBREVIATIONS = frozenset(
    {
        "al",
        "approx",
        "cf",
        "dept",
        "dr",
        "e.g",
        "eg",
        "est",
        "etc",
        "fig",
        "i.e",
        "ie",
        "inc",
        "jr",
        "mr",
        "mrs",
        "ms",
        "no",
        "p",
        "pp",
        "prof",
        "sr",
        "st",
        "vs",
    }
)

# Sentence boundary: terminal punctuation, whitespace, then a capital or digit
# (optionally behind an opening quote/bracket). Decimals never match because a
# decimal point has no trailing whitespace.
_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")
_TRAILING_WORD_RE = re.compile(r"([A-Za-z][A-Za-z.]*)\.$")
# Markdown headings are document structure (section titles, compare-mode
# document names), never claims; heading lines are discarded entirely.
_HEADING_LINE_RE = re.compile(r"^\s*#{1,6}\s")
# Markdown list markers and blockquote prefixes are noise for claim checking;
# strip them from the front of each line before splitting.
_LINE_NOISE_RE = re.compile(r"^\s*(?:[-*+]\s+|\d{1,3}[.)]\s+|>\s*)+")
# A compare answer is "## name" sections; heading lines delimit the sections.
_COMPARE_HEADING_RE = re.compile(r"^##\s[^\n]*$", re.MULTILINE)


@dataclass(frozen=True)
class VerifiedSource:
    document_id: str
    document_name: str
    page_number: int
    excerpt: str


@dataclass(frozen=True)
class VerifiedSentence:
    text: str
    verdict: Verdict
    score: float
    source: VerifiedSource | None


@dataclass(frozen=True)
class VerificationResult:
    message_id: str
    generated_at: datetime
    sentences: tuple[VerifiedSentence, ...]


_cache: OrderedDict[str, VerificationResult] = OrderedDict()
_cache_lock = threading.Lock()


def clear_verification_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _cache_get(cache_key: str) -> VerificationResult | None:
    with _cache_lock:
        result = _cache.get(cache_key)
        if result is not None:
            _cache.move_to_end(cache_key)
        return result


def _cache_put(cache_key: str, result: VerificationResult) -> None:
    with _cache_lock:
        _cache[cache_key] = result
        _cache.move_to_end(cache_key)
        while len(_cache) > _CACHE_LIMIT:
            _cache.popitem(last=False)


def split_sentences(text: str) -> list[str]:
    """Deterministic rule-based sentence splitter for Markdown answers.

    Splits on sentence-ending punctuation followed by whitespace and a capital
    letter or digit, protects common abbreviations and decimals, treats every
    line as its own segment, discards heading lines entirely, and drops
    Markdown list/blockquote prefixes.
    """
    sentences: list[str] = []
    for raw_line in text.splitlines():
        if _HEADING_LINE_RE.match(raw_line):
            continue
        line = _LINE_NOISE_RE.sub("", raw_line).strip()
        if not line or _HEADING_LINE_RE.match(line):
            continue
        start = 0
        for boundary in _BOUNDARY_RE.finditer(line):
            candidate = line[start : boundary.start()].strip()
            trailing = _TRAILING_WORD_RE.search(candidate)
            if trailing and trailing.group(1).lower() in _ABBREVIATIONS:
                continue
            if candidate:
                sentences.append(candidate)
            start = boundary.end()
        tail = line[start:].strip()
        if tail:
            sentences.append(tail)
    return sentences


def _scoring_text(sentence: str) -> str:
    """Sentence text used for embedding and overlap; citation markers are noise."""
    return CITATION_MARKER_RE.sub(" ", sentence).strip()


def _excerpt(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) > _EXCERPT_LIMIT:
        return collapsed[: _EXCERPT_LIMIT - 3] + "…"
    return collapsed


def _combined_score(sentence_tokens: set[str], match: VectorMatch) -> float:
    """Blend cosine similarity with the retrieval term-overlap heuristic."""
    cosine = max(0.0, min(1.0, match.score))
    chunk_tokens = content_tokens(match.text)
    overlap = len(sentence_tokens & chunk_tokens) / len(sentence_tokens) if sentence_tokens else 0.0
    return round(0.5 * cosine + 0.5 * overlap, 4)


def _verdict(score: float, settings: Settings) -> Verdict:
    if score >= settings.verification_supported_score:
        return "supported"
    if score >= settings.verification_weak_score:
        return "weak"
    return "unsupported"


def _scoped_document_ids(db: Session, message: Message) -> list[str]:
    """Selected conversation documents plus any documents the answer cited."""
    selected = db.scalars(
        select(ConversationDocument.document_id).where(
            ConversationDocument.conversation_id == message.conversation_id
        )
    )
    cited = (
        citation.document_id for citation in message.citations if citation.document_id is not None
    )
    return list(dict.fromkeys([*selected, *cited]))


def _cache_key(db: Session, settings: Settings, message: Message, document_ids: list[str]) -> str:
    """Key verdicts by everything they depend on, not just the message id.

    The scoped document ids and their latest ``updated_at`` capture index scope
    changes (reprocessing bumps ``updated_at``); the thresholds capture verdict
    boundary changes. Computing this is one cheap aggregate query.
    """
    latest_update: datetime | None = None
    if document_ids:
        latest_update = db.scalar(
            select(func.max(Document.updated_at)).where(Document.id.in_(document_ids))
        )
    return "|".join(
        [
            message.id,
            ",".join(sorted(document_ids)),
            latest_update.isoformat() if latest_update is not None else "",
            str(settings.verification_supported_score),
            str(settings.verification_weak_score),
        ]
    )


def _claim_text(message: Message, content: str) -> str:
    """Content that carries checkable claims.

    For compare answers, split on the ``## document`` section boundaries and
    drop every section whose body is the fixed insufficient-evidence refusal:
    refusals are canned application text, not claims about the documents.
    """
    if message.mode != COMPARE_MODE:
        return content
    sections = _COMPARE_HEADING_RE.split(content)
    kept = [
        section.strip()
        for section in sections
        if section.strip() and section.strip() != INSUFFICIENT_EVIDENCE
    ]
    return "\n\n".join(kept)


def verify_message(
    db: Session,
    settings: Settings,
    embeddings: EmbeddingProvider,
    vector_store: VectorStore,
    message: Message,
) -> VerificationResult:
    """Score each sentence of a persisted assistant answer against the documents."""
    document_ids = _scoped_document_ids(db, message)
    cache_key = _cache_key(db, settings, message, document_ids)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    content = message.content.strip()
    if not content or content in (INSUFFICIENT_EVIDENCE, GENERATION_FAILED_MESSAGE):
        result = VerificationResult(message_id=message.id, generated_at=utc_now(), sentences=())
        _cache_put(cache_key, result)
        return result

    candidates: list[tuple[str, set[str], str]] = []
    for sentence in split_sentences(_claim_text(message, content)):
        scoring_text = _scoring_text(sentence)
        tokens = content_tokens(scoring_text)
        if not tokens:
            continue
        candidates.append((sentence, tokens, scoring_text))

    verified: list[VerifiedSentence] = []
    if candidates:
        vectors = embeddings.embed([scoring_text for _, _, scoring_text in candidates])
        for (sentence, tokens, _), vector in zip(candidates, vectors, strict=True):
            matches = (
                vector_store.query(vector, document_ids, _CANDIDATES_PER_SENTENCE)
                if document_ids
                else []
            )
            best_score = 0.0
            best_match: VectorMatch | None = None
            for match in validate_matches(db, matches, document_ids):
                score = _combined_score(tokens, match)
                if best_match is None or score > best_score:
                    best_score = score
                    best_match = match
            verdict = _verdict(best_score, settings)
            source: VerifiedSource | None = None
            if best_match is not None and verdict != "unsupported":
                source = VerifiedSource(
                    document_id=str(best_match.metadata["document_id"]),
                    document_name=str(best_match.metadata["document_name"]),
                    page_number=int(best_match.metadata["page_number"]),
                    excerpt=_excerpt(best_match.text),
                )
            verified.append(
                VerifiedSentence(text=sentence, verdict=verdict, score=best_score, source=source)
            )

    result = VerificationResult(
        message_id=message.id, generated_at=utc_now(), sentences=tuple(verified)
    )
    _cache_put(cache_key, result)
    return result
