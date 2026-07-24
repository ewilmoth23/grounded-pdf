from pathlib import Path

from app.services.embeddings import DeterministicEmbeddingProvider
from app.services.vector_store import ChromaVectorStore, VectorRecord


def make_record(
    embeddings: DeterministicEmbeddingProvider,
    record_id: str,
    document_id: str,
    text: str,
) -> VectorRecord:
    return VectorRecord(
        id=record_id,
        text=text,
        embedding=embeddings.embed([text])[0],
        metadata={
            "document_id": document_id,
            "document_name": f"{document_id}.pdf",
            "page_number": 1,
            "chunk_index": 0,
            "chunk_id": record_id,
        },
    )


def test_chroma_persists_scopes_and_deletes_vectors(tmp_path: Path) -> None:
    embeddings = DeterministicEmbeddingProvider()
    path = tmp_path / "chroma"
    first = ChromaVectorStore(path)
    first.upsert(
        [
            make_record(embeddings, "alpha:1:0", "alpha", "alpha-only verified evidence"),
            make_record(embeddings, "beta:1:0", "beta", "beta-only private evidence"),
        ]
    )

    reopened = ChromaVectorStore(path)
    alpha_matches = reopened.query(
        embeddings.embed(["alpha-only verified evidence"])[0], ["alpha"], 5
    )
    assert [match.id for match in alpha_matches] == ["alpha:1:0"]
    assert {match.metadata["document_id"] for match in alpha_matches} == {"alpha"}

    reopened.delete_document("alpha")
    assert reopened.query(embeddings.embed(["alpha-only"])[0], ["alpha"], 5) == []
    assert reopened.query(embeddings.embed(["beta-only"])[0], ["beta"], 5)
