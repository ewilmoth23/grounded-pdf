"""Server-side conversation export.

Exports are rendered entirely from persisted records: the conversation row, its
messages in creation order, the application-owned citation rows, the runtime
settings snapshot, and per-answer verification summaries recomputed with
``verify_message``. Browser state is never a source. Both formats are written by
hand (no template engine): Markdown for editing, and a self-contained HTML file
with inline CSS and every piece of user or model content escaped.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.entities import Citation, Conversation, Message, MessageRole, utc_now
from app.rag.verification import verify_message
from app.services.embeddings import EmbeddingProvider
from app.services.vector_store import VectorStore

ExportFormat = Literal["markdown", "html"]

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Verification embeds every sentence of every answer; bound the work so huge
# conversations cannot pin a CPU for the duration of one export request.
VERIFIED_MESSAGE_LIMIT = 50

LOCAL_SOURCES_NOTE = (
    "Citations reference local documents on the machine where this conversation was created."
)
VERIFICATION_UNAVAILABLE_NOTE = (
    "Verification was unavailable when this export was generated, so claim summaries are omitted."
)
VERIFICATION_TRUNCATED_NOTE = (
    f"Verification shown for the {VERIFIED_MESSAGE_LIMIT} most recent answers."
)


@dataclass(frozen=True)
class ConversationExport:
    content: str
    media_type: str
    filename: str


def slugify_title(title: str) -> str:
    """Reduce a conversation title to a header-injection-safe [a-z0-9-] slug."""
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")
    return slug[:80].strip("-") or "conversation"


def _timestamp(generated_at: datetime) -> str:
    return generated_at.strftime("%Y-%m-%d %H:%M UTC")


def _inline(text: str) -> str:
    """Collapse content into a single line for headings."""
    return " ".join(text.split())


def _citation_marker(citation: Citation) -> str:
    return f"[{citation.document_name}, p. {citation.page_number}]"


def _settings_lines(settings: Settings) -> list[str]:
    return [
        f"Provider: {settings.model_provider}",
        f"Model: {settings.model_name}",
        f"Embedding model: {settings.embedding_model}",
        f"Chunk size: {settings.chunk_size} characters",
        f"Chunk overlap: {settings.chunk_overlap} characters",
        f"Passages retrieved per question: {settings.retrieval_count}",
        f"Temperature: {settings.temperature}",
        f"Max output tokens: {settings.max_output_tokens}",
    ]


def _verification_summaries(
    db: Session,
    settings: Settings,
    embeddings: EmbeddingProvider,
    vector_store: VectorStore,
    messages: list[Message],
) -> tuple[dict[str, str], bool, bool]:
    """Summary lines per assistant message, plus degraded and truncated flags.

    Verification depends on the embedding provider and vector store; if either
    fails the export must still succeed, so the first failure stops further
    attempts and the document carries a note instead of summaries. Only the
    most recent ``VERIFIED_MESSAGE_LIMIT`` assistant messages are verified.
    """
    assistant_messages = [message for message in messages if message.role == MessageRole.ASSISTANT]
    truncated = len(assistant_messages) > VERIFIED_MESSAGE_LIMIT
    summaries: dict[str, str] = {}
    for message in assistant_messages[-VERIFIED_MESSAGE_LIMIT:]:
        try:
            result = verify_message(db, settings, embeddings, vector_store, message)
        except Exception:
            return summaries, True, truncated
        total = len(result.sentences)
        if total == 0:
            continue
        supported = sum(1 for sentence in result.sentences if sentence.verdict == "supported")
        noun = "claim" if total == 1 else "claims"
        summaries[message.id] = f"Verification: {supported} of {total} {noun} supported"
    return summaries, False, truncated


def _render_markdown(
    conversation: Conversation,
    settings: Settings,
    summaries: dict[str, str],
    verification_unavailable: bool,
    verification_truncated: bool,
    generated_at: datetime,
) -> str:
    lines: list[str] = [
        f"# {_inline(conversation.title)}",
        "",
        f"Exported {_timestamp(generated_at)} — {settings.app_name} v{settings.version}",
        "",
    ]
    for message in conversation.messages:
        if message.role == MessageRole.USER:
            lines.extend([f"## Q: {_inline(message.content)}", ""])
            continue
        lines.extend([message.content.strip(), ""])
        summary = summaries.get(message.id)
        if summary:
            lines.extend([summary, ""])
        if message.citations:
            lines.extend(["### Sources", ""])
            for citation in message.citations:
                lines.append(
                    f"{citation.ordinal}. {_citation_marker(citation)} — "
                    f"{citation.document_name}, page {citation.page_number}"
                )
                lines.extend(["", f"   > {_inline(citation.excerpt)}", ""])
    lines.extend(["---", "", "## Generation settings", ""])
    lines.extend(f"- {line}" for line in _settings_lines(settings))
    lines.extend(["", LOCAL_SOURCES_NOTE])
    if verification_truncated:
        lines.extend(["", VERIFICATION_TRUNCATED_NOTE])
    if verification_unavailable:
        lines.extend(["", VERIFICATION_UNAVAILABLE_NOTE])
    return "\n".join(lines) + "\n"


_HTML_STYLE = """
  :root { color-scheme: light; }
  body {
    margin: 0;
    padding: 2.5rem 1.25rem 4rem;
    background: #fff;
    color: #1f2430;
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    line-height: 1.65;
  }
  main { max-width: 46rem; margin: 0 auto; }
  h1 { font-size: 1.6rem; line-height: 1.3; margin: 0 0 0.25rem; }
  h2 { font-size: 1.15rem; margin: 2.25rem 0 0.75rem; }
  h3 { font-size: 0.95rem; margin: 1.5rem 0 0.5rem; }
  .meta, footer { color: #5b6272; font-size: 0.85rem; }
  .answer p { margin: 0.75rem 0; white-space: pre-wrap; }
  .verification { font-size: 0.85rem; color: #5b6272; }
  ol.sources { padding-left: 1.4rem; margin: 0.5rem 0; }
  ol.sources li { margin: 0.75rem 0; }
  .marker { font-weight: 600; }
  blockquote {
    margin: 0.5rem 0 0;
    padding: 0.25rem 0 0.25rem 0.9rem;
    border-left: 3px solid #c7cad3;
    color: #454b5a;
    font-size: 0.9rem;
  }
  hr { border: 0; border-top: 1px solid #e3e5ea; margin: 2.5rem 0 1.5rem; }
  footer ul { padding-left: 1.4rem; margin: 0.5rem 0; }
""".strip("\n")


_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_MD_LIST_ITEM_RE = re.compile(r"^(?:[-*]|\d{1,3}[.)])\s+(.*)$")
_MD_QUOTE_RE = re.compile(r"^>\s?(.*)$")
_MD_CODE_RE = re.compile(r"`([^`\n]+)`")
_MD_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")


def _inline_html(text: str) -> str:
    """Escape everything first, then wrap the supported inline Markdown spans."""
    escaped = html.escape(text)
    escaped = _MD_CODE_RE.sub(lambda match: f"<code>{match.group(1)}</code>", escaped)
    escaped = _MD_BOLD_RE.sub(lambda match: f"<strong>{match.group(1)}</strong>", escaped)
    return _MD_ITALIC_RE.sub(lambda match: f"<em>{match.group(1)}</em>", escaped)


def _answer_html(text: str) -> str:
    """Minimal Markdown renderer for answer content — no dependency, no raw HTML.

    Supports the constructs answers actually use: ``#`` to ``######`` headings
    (rendered as ``h3``/``h4`` so the export's own ``h1``/``h2`` hierarchy is
    preserved), ``-``/``*`` bullet and numbered lists, bold, italic, inline
    code, blockquotes, and plain paragraphs. Every character is HTML-escaped
    before any wrapping.
    """
    parts: list[str] = []
    open_list: str | None = None
    paragraph: list[str] = []
    quote: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            parts.append(f"<p>{_inline_html(' '.join(paragraph))}</p>")
            paragraph = []

    def flush_quote() -> None:
        nonlocal quote
        if quote:
            parts.append(f"<blockquote>{_inline_html(' '.join(quote))}</blockquote>")
            quote = []

    def close_list() -> None:
        nonlocal open_list
        if open_list is not None:
            parts.append(f"</{open_list}>")
            open_list = None

    for raw_line in text.strip().splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_quote()
            close_list()
            continue
        heading = _MD_HEADING_RE.match(line)
        if heading:
            flush_paragraph()
            flush_quote()
            close_list()
            tag = "h3" if len(heading.group(1)) <= 2 else "h4"
            parts.append(f"<{tag}>{_inline_html(heading.group(2).strip())}</{tag}>")
            continue
        list_item = _MD_LIST_ITEM_RE.match(line)
        if list_item:
            flush_paragraph()
            flush_quote()
            tag = "ul" if line[0] in "-*" else "ol"
            if open_list != tag:
                close_list()
                parts.append(f"<{tag}>")
                open_list = tag
            parts.append(f"<li>{_inline_html(list_item.group(1).strip())}</li>")
            continue
        quote_line = _MD_QUOTE_RE.match(line)
        if quote_line:
            flush_paragraph()
            close_list()
            quote.append(quote_line.group(1).strip())
            continue
        flush_quote()
        close_list()
        paragraph.append(line)
    flush_paragraph()
    flush_quote()
    close_list()
    return "".join(parts)


def _render_html(
    conversation: Conversation,
    settings: Settings,
    summaries: dict[str, str],
    verification_unavailable: bool,
    verification_truncated: bool,
    generated_at: datetime,
) -> str:
    title = html.escape(_inline(conversation.title))
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{title}</title>",
        f"<style>\n{_HTML_STYLE}\n</style>",
        "</head>",
        "<body>",
        "<main>",
        f"<h1>{title}</h1>",
        (
            f'<p class="meta">Exported {html.escape(_timestamp(generated_at))} — '
            f"{html.escape(settings.app_name)} v{html.escape(settings.version)}</p>"
        ),
    ]
    for message in conversation.messages:
        if message.role == MessageRole.USER:
            parts.append(f"<h2>Q: {html.escape(_inline(message.content))}</h2>")
            continue
        parts.append(f'<div class="answer">{_answer_html(message.content)}</div>')
        summary = summaries.get(message.id)
        if summary:
            parts.append(f'<p class="verification">{html.escape(summary)}</p>')
        if message.citations:
            parts.append("<h3>Sources</h3>")
            parts.append('<ol class="sources">')
            for citation in message.citations:
                parts.append(
                    "<li>"
                    f'<span class="marker">{html.escape(_citation_marker(citation))}</span> '
                    f"{html.escape(citation.document_name)}, page {citation.page_number}"
                    f"<blockquote>{html.escape(_inline(citation.excerpt))}</blockquote>"
                    "</li>"
                )
            parts.append("</ol>")
    parts.extend(["<hr>", "<footer>", "<h2>Generation settings</h2>", "<ul>"])
    parts.extend(f"<li>{html.escape(line)}</li>" for line in _settings_lines(settings))
    parts.append("</ul>")
    parts.append(f"<p>{html.escape(LOCAL_SOURCES_NOTE)}</p>")
    if verification_truncated:
        parts.append(f"<p>{html.escape(VERIFICATION_TRUNCATED_NOTE)}</p>")
    if verification_unavailable:
        parts.append(f"<p>{html.escape(VERIFICATION_UNAVAILABLE_NOTE)}</p>")
    parts.extend(["</footer>", "</main>", "</body>", "</html>"])
    return "\n".join(parts) + "\n"


def build_export(
    db: Session,
    settings: Settings,
    embeddings: EmbeddingProvider,
    vector_store: VectorStore,
    conversation: Conversation,
    export_format: ExportFormat,
) -> ConversationExport:
    """Render a conversation export from persisted records only."""
    generated_at = utc_now()
    summaries, verification_unavailable, verification_truncated = _verification_summaries(
        db, settings, embeddings, vector_store, list(conversation.messages)
    )
    if export_format == "html":
        content = _render_html(
            conversation,
            settings,
            summaries,
            verification_unavailable,
            verification_truncated,
            generated_at,
        )
        media_type = "text/html; charset=utf-8"
        extension = "html"
    else:
        content = _render_markdown(
            conversation,
            settings,
            summaries,
            verification_unavailable,
            verification_truncated,
            generated_at,
        )
        media_type = "text/markdown; charset=utf-8"
        extension = "md"
    filename = f"{slugify_title(conversation.title)}-{generated_at.date().isoformat()}.{extension}"
    return ConversationExport(content=content, media_type=media_type, filename=filename)
