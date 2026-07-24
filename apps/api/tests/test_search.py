from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.entities import Document, DocumentChunk, DocumentPage, ProcessingStatus
from app.services.dependencies import get_vector_store
from app.services.embeddings import DeterministicEmbeddingProvider
from app.services.vector_store import VectorRecord


def seed_document(
    db: Session,
    name: str,
    text: str,
    page_number: int = 1,
    status: ProcessingStatus = ProcessingStatus.READY,
) -> DocumentChunk:
    document = Document(
        original_name=name,
        storage_name=f"{name}.stored",
        file_size=100,
        sha256=name.ljust(64, "0")[:64],
        status=status,
        page_count=1,
        searchable_page_count=1,
    )
    db.add(document)
    db.flush()
    page = DocumentPage(
        document_id=document.id,
        page_number=page_number,
        raw_text=text,
        normalized_text=text,
        is_searchable=True,
        character_count=len(text),
    )
    db.add(page)
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        page_id=page.id,
        page_number=page_number,
        chunk_index=0,
        raw_text=text,
        normalized_text=text,
        start_offset=0,
        end_offset=len(text),
        embedding_id=f"{document.id}:{page_number}:0",
    )
    db.add(chunk)
    db.commit()
    return chunk


def index_chunk(provider: DeterministicEmbeddingProvider, chunk: DocumentChunk) -> None:
    get_vector_store().upsert(
        [
            VectorRecord(
                id=chunk.embedding_id,
                text=chunk.normalized_text,
                embedding=provider.embed([chunk.normalized_text])[0],
                # Deliberately wrong name: responses must come from relational rows.
                metadata={"document_id": chunk.document_id, "document_name": "tampered.pdf"},
            )
        ]
    )


def test_search_returns_relational_matches_sorted_by_score(client: TestClient, db: Session) -> None:
    provider = DeterministicEmbeddingProvider()
    strong = seed_document(
        db, "pilot.pdf", "The measured efficiency gain was 37 percent.", page_number=2
    )
    weak = seed_document(db, "notes.pdf", "The efficiency team met on a Tuesday.", page_number=5)
    index_chunk(provider, strong)
    index_chunk(provider, weak)

    response = client.get("/api/v1/search", params={"q": "measured efficiency gain"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "measured efficiency gain"
    assert payload["documents_available"] is True
    matches = payload["matches"]
    assert matches
    assert matches[0]["document_id"] == strong.document_id
    assert matches[0]["document_name"] == "pilot.pdf"
    assert matches[0]["page_number"] == 2
    assert matches[0]["excerpt"] == "The measured efficiency gain was 37 percent."
    assert 0.0 <= matches[0]["score"] <= 1.0
    scores = [match["score"] for match in matches]
    assert scores == sorted(scores, reverse=True)
    # Vector metadata is never trusted for display fields.
    assert all(match["document_name"] != "tampered.pdf" for match in matches)


def test_search_scope_excludes_unselected_documents(client: TestClient, db: Session) -> None:
    provider = DeterministicEmbeddingProvider()
    selected = seed_document(db, "alpha.pdf", "The pilot efficiency gain was 37 percent.")
    unselected = seed_document(db, "beta.pdf", "The pilot efficiency gain was 99 percent.")
    index_chunk(provider, selected)
    index_chunk(provider, unselected)

    response = client.get(
        "/api/v1/search",
        params={"q": "pilot efficiency gain", "document_ids": [selected.document_id]},
    )

    assert response.status_code == 200
    matches = response.json()["matches"]
    assert matches
    assert {match["document_id"] for match in matches} == {selected.document_id}
    assert all(match["document_id"] != unselected.document_id for match in matches)


def test_search_excludes_documents_that_are_not_ready(client: TestClient, db: Session) -> None:
    provider = DeterministicEmbeddingProvider()
    ready = seed_document(db, "ready.pdf", "The pilot efficiency gain was 37 percent.")
    processing = seed_document(
        db,
        "processing.pdf",
        "The pilot efficiency gain was 42 percent.",
        status=ProcessingStatus.PROCESSING,
    )
    index_chunk(provider, ready)
    index_chunk(provider, processing)

    response = client.get("/api/v1/search", params={"q": "pilot efficiency gain"})

    assert response.status_code == 200
    matches = response.json()["matches"]
    assert matches
    assert {match["document_id"] for match in matches} == {ready.document_id}


def test_search_drops_vector_matches_without_relational_chunks(
    client: TestClient, db: Session
) -> None:
    provider = DeterministicEmbeddingProvider()
    chunk = seed_document(db, "trusted.pdf", "The verified result was 37 percent.")
    index_chunk(provider, chunk)
    stale_text = "The verified result was 37 percent."
    get_vector_store().upsert(
        [
            VectorRecord(
                id="stale-embedding-id",
                text=stale_text,
                embedding=provider.embed([stale_text])[0],
                metadata={"document_id": chunk.document_id, "document_name": "trusted.pdf"},
            )
        ]
    )

    response = client.get("/api/v1/search", params={"q": "verified result"})

    assert response.status_code == 200
    matches = response.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["document_id"] == chunk.document_id


def test_search_rejects_missing_or_blank_queries(client: TestClient) -> None:
    for params in (None, {"q": ""}, {"q": "   "}):
        response = client.get("/api/v1/search", params=params)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def test_search_reports_when_no_ready_documents_exist(client: TestClient, db: Session) -> None:
    response = client.get("/api/v1/search", params={"q": "anything at all"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["documents_available"] is False
    assert payload["matches"] == []


def test_search_rejects_oversized_document_filters(client: TestClient) -> None:
    response = client.get(
        "/api/v1/search",
        params={"q": "anything", "document_ids": [f"doc-{index}" for index in range(51)]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
