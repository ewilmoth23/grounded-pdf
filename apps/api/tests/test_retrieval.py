from app.core.config import Settings
from app.rag.grounding import (
    StreamingCitationFilter,
    build_citations,
    ensure_inline_citation,
    select_cited_matches,
)
from app.rag.retrieval import Retriever
from app.services.embeddings import DeterministicEmbeddingProvider
from app.services.vector_store import InMemoryVectorStore, VectorMatch, VectorRecord


def make_record(
    provider: DeterministicEmbeddingProvider, record_id: str, document_id: str, text: str, page: int
) -> VectorRecord:
    return VectorRecord(
        id=record_id,
        text=text,
        embedding=provider.embed([text])[0],
        metadata={
            "document_id": document_id,
            "document_name": f"{document_id}.pdf",
            "page_number": page,
            "chunk_index": 0,
            "chunk_id": record_id,
        },
    )


def test_retrieval_is_restricted_to_selected_documents(settings: Settings) -> None:
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore()
    store.upsert(
        [
            make_record(provider, "a1", "alpha", "The pilot efficiency gain was 37 percent.", 2),
            make_record(provider, "b1", "beta", "The pilot efficiency gain was 99 percent.", 9),
        ]
    )
    matches = Retriever(settings, provider, store).retrieve(
        "What was the efficiency gain?", ["alpha"]
    )
    assert matches
    assert {match.metadata["document_id"] for match in matches} == {"alpha"}


def test_no_answer_when_score_is_below_threshold(settings: Settings) -> None:
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore()
    store.upsert([make_record(provider, "a1", "alpha", "Oranges and apples.", 1)])
    strict = settings.model_copy(update={"retrieval_min_score": 0.99})
    assert Retriever(strict, provider, store).retrieve("Quantum mechanics", ["alpha"]) == []


def test_unrelated_question_requires_meaningful_evidence(settings: Settings) -> None:
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore()
    store.upsert(
        [
            make_record(
                provider,
                "a1",
                "alpha",
                "The pilot measured a 37 percent efficiency gain.",
                2,
            )
        ]
    )
    matches = Retriever(settings, provider, store).retrieve(
        "Who won the lunar chess championship on Mars?", ["alpha"]
    )
    assert matches == []


def test_structured_citations_come_from_retrieval_metadata(settings: Settings) -> None:
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore()
    store.upsert([make_record(provider, "a1", "alpha", "Supported evidence is here.", 7)])
    matches = store.query(provider.embed(["Supported evidence"])[0], ["alpha"], 1)
    citations = build_citations(matches)
    assert citations[0].document_id == "alpha"
    assert citations[0].page_number == 7
    assert citations[0].marker == "[alpha.pdf, p. 7]"
    assert ensure_inline_citation("An answer.", citations).endswith("[alpha.pdf, p. 7]")


def test_untrusted_inline_citation_markers_are_removed(settings: Settings) -> None:
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore()
    store.upsert([make_record(provider, "a1", "alpha", "Supported evidence is here.", 7)])
    citations = build_citations(
        store.query(provider.embed(["Supported evidence"])[0], ["alpha"], 1)
    )

    answer = ensure_inline_citation(
        (
            "Supported answer [1] [Source 2] [invented.pdf, p. 999] "
            "(ALPHA.PDF, P. 7) [alpha.pdf, p. 7]"
        ),
        citations,
    )

    assert "invented.pdf" not in answer
    assert "[1]" not in answer
    assert "[Source 2]" not in answer
    assert "(ALPHA.PDF, P. 7)" not in answer
    assert answer.endswith("[alpha.pdf, p. 7]")


def test_hash_prefixed_marker_is_stripped_from_the_persisted_answer(
    settings: Settings,
) -> None:
    """Regression: a hash-prefixed marker reached the stored answer and polluted
    the claim string sent to the verifier, downgrading a supported fact to a weak
    match against the wrong page."""
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore()
    store.upsert([make_record(provider, "a1", "alpha", "Supported evidence is here.", 7)])
    citations = build_citations(
        store.query(provider.embed(["Supported evidence"])[0], ["alpha"], 1)
    )

    answer = ensure_inline_citation(
        "37 percent #alpha.pdf, p. 7 [alpha.pdf, p. 7]",
        citations,
    )

    assert "#alpha.pdf" not in answer
    assert answer.count("[alpha.pdf, p. 7]") == 1
    assert answer.startswith("37 percent [")
    assert "  " not in answer


def test_markdown_headings_survive_hash_marker_stripping(settings: Settings) -> None:
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore()
    store.upsert([make_record(provider, "a1", "alpha", "Supported evidence is here.", 7)])
    citations = build_citations(
        store.query(provider.embed(["Supported evidence"])[0], ["alpha"], 1)
    )

    answer = ensure_inline_citation(
        "# Findings\n\nThe gain held, p. 7 of the brief. [alpha.pdf, p. 7]",
        citations,
    )

    assert answer.startswith("# Findings")


def test_untrusted_citation_markers_are_filtered_across_stream_tokens(
    settings: Settings,
) -> None:
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore()
    store.upsert([make_record(provider, "a1", "alpha", "Supported evidence is here.", 7)])
    citations = build_citations(
        store.query(provider.embed(["Supported evidence"])[0], ["alpha"], 1)
    )
    citation_filter = StreamingCitationFilter(citations)

    tokens = [
        "Supported [1] [Source",
        " 2] [invented",
        ".pdf, p. 999] (ALPHA.PDF, P. 7) answer [alpha",
        ".pdf, p. 7]",
    ]
    streamed = "".join(citation_filter.feed(token) for token in tokens) + citation_filter.finish()

    assert " ".join(streamed.split()) == "Supported answer [alpha.pdf, p. 7]"


def test_incomplete_untrusted_citations_are_not_streamed_or_persisted(
    settings: Settings,
) -> None:
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore()
    store.upsert([make_record(provider, "a1", "alpha", "Supported evidence is here.", 7)])
    citations = build_citations(
        store.query(provider.embed(["Supported evidence"])[0], ["alpha"], 1)
    )
    citation_filter = StreamingCitationFilter(citations)

    streamed = citation_filter.feed("Supported answer [invented.pdf, p. 999")
    streamed += citation_filter.finish()
    finalized = ensure_inline_citation("Supported answer [invented.pdf, p. 999", citations)

    assert streamed == "Supported answer "
    assert "invented.pdf" not in finalized
    assert finalized == "Supported answer [alpha.pdf, p. 7]"


def test_internal_grounding_wrapper_is_normalized_to_database_citation(
    settings: Settings,
) -> None:
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore()
    store.upsert([make_record(provider, "a1", "alpha", "Supported evidence is here.", 7)])
    citations = build_citations(
        store.query(provider.embed(["Supported evidence"])[0], ["alpha"], 1)
    )
    raw_answer = "Supported answer. (GROUNDING: [alpha.pdf, p. 7])"

    citation_filter = StreamingCitationFilter(citations)
    streamed = citation_filter.feed(raw_answer) + citation_filter.finish()
    finalized = ensure_inline_citation(raw_answer, citations)

    assert streamed == "Supported answer. [alpha.pdf, p. 7]"
    assert finalized == "Supported answer. [alpha.pdf, p. 7]"
    assert "GROUNDING:" not in streamed


def test_model_context_excludes_matches_without_structured_citations(settings: Settings) -> None:
    matches = [
        VectorMatch(
            id=f"record-{page}",
            text=f"Evidence from page {page}",
            metadata={
                "document_id": "alpha",
                "document_name": "alpha.pdf",
                "page_number": page,
            },
            score=0.9,
        )
        for page in range(1, 8)
    ]
    citations = build_citations(matches)

    cited_matches = select_cited_matches(matches, citations)

    assert len(citations) == 6
    assert {match.metadata["page_number"] for match in cited_matches} == set(range(1, 7))
