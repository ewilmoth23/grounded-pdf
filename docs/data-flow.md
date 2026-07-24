# Data flow

## Upload to ingestion

```mermaid
sequenceDiagram
  actor User
  participant Web
  participant API
  participant PDF as PyMuPDF
  participant DB as SQLite
  participant Embed as sentence-transformers
  participant Vector as Chroma

  User->>Web: Select one or more PDFs
  Web->>API: multipart upload
  API->>API: Enforce size, extension, signature, structure
  API->>API: Store under collision-safe UUID name
  API->>DB: Create queued document + checksum
  API-->>Web: 202 and per-file results
  API->>DB: Mark processing and create attempt
  API->>PDF: Extract metadata and text page by page
  PDF-->>API: Page text and page numbers
  API->>DB: Replace pages and chunks idempotently
  API->>Embed: Embed normalized page-bounded chunks
  Embed-->>API: Local vectors
  API->>Vector: Upsert stable embedding IDs + source metadata
  API->>DB: Mark ready only after vector success
  Web->>API: Poll processing status
```

Unsupported files are rejected before a database record is created. Duplicate checksums reuse the
existing record and discard the temporary upload; if that record's trusted stored file is missing, the
new upload restores it and requeues ingestion. Pages below the searchable character threshold are
stored with `is_searchable=false`; when optional OCR is enabled, those pages are rendered locally and
sent to Tesseract before being classified as unsearchable.

## Question to answer

```mermaid
sequenceDiagram
  actor User
  participant Web
  participant API
  participant DB as SQLite
  participant Vector as Chroma
  participant Model as Chat provider

  User->>Web: Ask a question
  Web->>API: POST stream with question only
  API->>DB: Load conversation's selected ready documents
  API->>DB: Persist user message
  API->>Vector: Similarity search filtered by selected document IDs
  Vector-->>API: Candidate chunk identifiers and scores
  API->>DB: Resolve candidates to selected relational chunks
  API->>API: Discard stale metadata, threshold, deduplicate, diversify
  alt No acceptable evidence
    API-->>Web: Stream deterministic insufficient-evidence response
  else Evidence found
    API->>API: Build source blocks and structured citations
    API->>Model: Grounding policy + sources + question
    Model-->>API: Answer tokens
    API-->>Web: SSE token events
    API->>API: Ensure at least one source marker
  end
  API->>DB: Persist assistant message and citation rows
  API-->>Web: Final typed message event
```

## Citation construction

```mermaid
flowchart LR
  Chunk["Retrieved vector identifier"] --> Database["Selected relational chunk + document"]
  Database --> Metadata["document_id, name, page, text + vector score"]
  Metadata --> Dedup["Unique document/page pairs"]
  Dedup --> Citation["Application-owned Citation row"]
  Citation --> Marker["Stable inline marker"]
  Citation --> Card["Web source card"]
  Card --> File["Safe PDF endpoint"]
  File --> Page["PDF.js cited-page navigation"]
  Page --> Highlight["Text-layer excerpt highlight"]
```

The model can repeat a supplied marker, but it cannot create the citation object's document ID, file
URL, page target, excerpt, score, or ordinal. Those values come from the retrieval record.

When a source card opens the viewer, the citation's excerpt travels with the navigation (router
state, with a truncated `highlight` search parameter as a fallback). The viewer normalizes the
excerpt and the PDF.js text-layer strings (case, whitespace, ligatures, end-of-line hyphenation),
locates the excerpt — exact match first, then the longest shared run when extraction and the text
layer disagree — and wraps the matched characters in highlight marks before scrolling the first one
into view. This is presentation only: the browser never supplies citation data, and when no reliable
match exists (typically scanned or OCR pages) the viewer keeps the page-level indicator and shows
"Evidence is on this page; exact position unavailable."

## Deletion

```mermaid
flowchart TD
  Request["Delete document"] --> Resolve["Resolve document by ID"]
  Resolve --> Tombstone["Commit deleted tombstone"]
  Tombstone --> Vector["Delete vectors by trusted document_id"]
  Vector --> File["Delete validated UUID storage path"]
  File --> Database["Delete document row"]
  Database --> Cascade["Cascade pages, chunks, jobs, selections, citations"]
  Cascade --> Commit["Commit and acknowledge"]
```

The durable tombstone is committed before external cleanup. If vector, file, or final relational
cleanup fails, the API keeps the tombstone with a retry message instead of claiming complete deletion.
Deletion is rejected while ingestion is queued or processing so a worker cannot recreate vectors
after cleanup.
