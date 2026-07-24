# Changelog

All notable changes to GroundedPDF are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use semantic versioning.

## v0.2.0 - 2026-07-24

### Changed

- Verification results are now cached by message id plus the scoped document ids, their latest
  `updated_at`, and the verdict thresholds (instead of the message id alone), and the cache is
  cleared on document deletion, bulk reprocessing, and settings changes, so cached verdicts can no
  longer outlive the evidence they were computed from. The web verification panel refreshes after
  five minutes instead of caching forever.
- Conversation exports verify at most the 50 most recent answers and note the truncation in both
  formats, HTML exports render answer Markdown (headings, lists, bold/italic/inline code,
  blockquotes) as real, fully escaped HTML elements instead of literal text, and
  `POST /documents/reprocess-stale` queues at most 25 documents per call and reports
  `{queued, remaining}` so clients can keep going until nothing stale remains.
- The chat provider cache is a four-entry LRU; evicted providers are parked and their shared HTTP
  clients closed on application shutdown, so repeated settings changes cannot leak connection
  pools. `GET /search` rejects more than 50 `document_ids` filters.
- `GET /documents`, `GET /conversations`, and `GET /conversations/{id}/messages` accept `limit`
  (default 100, maximum 500) and `offset` query parameters, return a deterministic order with a
  stable tiebreaker, and report the total row count in an `X-Total-Count` response header. The
  response body stays a plain array, so existing clients are unaffected.
- Citation snapshots survive document deletion (migration 0004): `citations.document_id` is now
  nullable with `ON DELETE SET NULL`, so deleting a document severs the link while the stored
  document name, page number, and excerpt keep historical answers renderable. Source cards for
  deleted documents render as non-clickable snapshots with a "Source deleted" note.
- Model providers reuse one shared HTTP client per provider configuration instead of opening a new
  connection pool for every request or health check; the clients are closed on application
  shutdown. Request timeouts are unchanged and still applied per request.
- Ingestion embeds and upserts chunks in 256-chunk batches, and the OCR path renders pages from the
  already-open PDF instead of reopening the file once per scanned page.
- Interactive API docs (`/docs`, `/redoc`) and `/openapi.json` are served only outside the
  production environment.

### Fixed

- Compare answers no longer poison verification: Markdown heading lines (including the per-document
  `## name` section titles) are never treated as claims, refusal sections and the fixed
  generation-failure placeholder are skipped entirely, so "Verify answer" and export summaries
  score only real evidence-bearing sentences.
- The web client pages through `/documents` and `/conversations` using `X-Total-Count` instead of
  silently truncating libraries at 100 entries, and after a stream error the chat refetches the
  persisted transcript (which includes the failure placeholder) instead of diverging from the
  server.
- ⌘K/Ctrl+K no longer hijacks focus while typing in an input, textarea, select, or contenteditable
  element, and only prevents the browser default when it actually handles the shortcut.
- PDF evidence highlighting rejects fallback matches that cover less than half of the cited
  excerpt (and bounds matching to the first 600 normalized characters), preventing a short generic
  overlap from highlighting the wrong passage. The search page now distinguishes "no documents
  uploaded" from "the selected document filter matched nothing ready".
- Failed answer generation no longer leaves an orphaned question: if retrieval fails, the pending
  user message is rolled back; if generation or persistence fails after the question was saved, a
  fixed "Answer generation failed. Ask again to retry." assistant placeholder is recorded so the
  conversation history stays complete. Cancelled streams are unchanged.

- Oversized chunked uploads now return the intended `413 upload_batch_too_large` response through
  the full production middleware stack instead of a 500.
- SQLite connections enable WAL journaling, a busy timeout, and normal synchronous mode so
  background ingestion no longer contends with request handlers.
- Health checks report a degraded vector store instead of failing with a 500 when Chroma raises an
  unexpected error, and unexpected worker failures now mark documents as failed with an error.
- The initial Alembic migration matches the ORM models exactly (non-native enums, naive UTC
  datetimes) and is exercised by an automated upgrade-and-compare test.
- Blocking retrieval, embedding, persistence, and upload work moved off the event loop into the
  request threadpool.
- Frontend stream reader releases its connection on error paths, the SSE parser tolerates CRLF and
  spec-optional field syntax, and API error handling no longer crashes on non-standard bodies.
- Dark mode now applies on every page (with a pre-paint theme script), and low-contrast text was
  raised to meet WCAG AA in both themes.

### Added

- Document outline navigation: ingestion captures the PDF bookmark tree (bounded to 500 entries
  with clamped page targets, stored as JSON on the document via migration 0003), the document
  detail endpoint serves it, and the viewer gains a collapsible outline sidebar — a persistent
  left panel on large screens and a toggleable sheet below — whose entries indent by depth, jump
  to the selected page, and highlight the section containing the current page. Documents without
  bookmarks show no outline control.
- Safe re-indexing: every successful ingestion records an index fingerprint (embedding model plus
  chunk size and overlap, migration 0003). Ready documents whose fingerprint no longer matches
  the effective runtime settings — including legacy documents indexed before fingerprints — are
  reported as `stale_index` in document responses, flagged with an "Index outdated" chip, and
  summarized in a Documents banner offering one-click bulk reprocessing.
  `POST /documents/reprocess-stale` atomically claims each stale ready document through the
  existing retry lifecycle (queued and failed documents are untouched) and re-ingestion fully
  replaces the previous chunks and vectors. Settings notes that chunk changes require
  reprocessing.
- Grounded export: `GET /conversations/{id}/export?format=markdown|html` downloads a conversation
  as Markdown or a self-contained HTML file (inline CSS, no scripts, all content escaped) with the
  questions, answers, numbered citations (marker, document, page, excerpt), a per-answer
  "Verification: N of M claims supported" summary, and a generation-settings footer. The export is
  rendered server-side from persisted records only; if verification infrastructure is unavailable
  the file notes that instead of failing. The chat header gains an Export menu, disabled while
  streaming or before the first saved message.
- Cross-document compare mode: a composer toggle asks one question across two to four selected
  documents. Retrieval runs separately per document, each section streams through its own citation
  filter with only that document's markers, and a document without admissible evidence gets the
  fixed insufficient-evidence response in its section without a provider call. Compare answers
  render as side-by-side per-document panels on large screens (stacked on mobile) over the
  existing SSE protocol, and a nullable `mode` column on messages (migration 0002) records how a
  message was produced.
- Instant semantic quote search: a Search page (⌘K / Ctrl+K from anywhere) embeds the query
  locally and returns exact stored passages — document, page badge, excerpt with the query terms
  emphasized, and a match-strength indicator — each deep-linking into the highlighted PDF viewer.
  The `GET /search` endpoint is retrieval-only: every vector match is revalidated against
  relational chunk records, no chat provider is involved, and nothing is generated.
- Claim-level verification: a "Verify answer" action on each completed assistant message splits
  the saved answer into sentences with a deterministic rule-based splitter, scores each sentence
  against the conversation's documents (cosine similarity plus term overlap), and renders a
  supported / weak match / not found panel with unsupported claims first and evidence links into
  the highlighted viewer. Verification is a read-only lens: it never changes the answer, and
  results are cached in-process per message.
- Exact evidence highlighting: source cards now open the cited page with the cited passage
  highlighted in the PDF text layer and scrolled into view. Matching normalizes case, whitespace,
  ligatures, and end-of-line hyphenation, with a longest-shared-run fallback when extraction and
  the text layer disagree. When the passage cannot be located (typically scanned or OCR pages),
  the viewer keeps the page-level citation and states that the exact position is unavailable.
- Styled Markdown rendering for answers via `@tailwindcss/typography` and a self-hosted Inter
  variable font.
- Conversation auto-titling from the first question, a stop-generation control, restored composer
  text after failed sends, and scroll pinning with a jump-to-latest control.
- Accessible dialogs replacing native `prompt`/`confirm`, inline conversation rename, structural
  shimmer skeletons, a true indeterminate processing bar, suggested prompts on the empty chat
  state, an app error boundary, a favicon, and reduced-motion support.
- A global 1 MiB request-body cap for non-upload endpoints, a bounded rate-limiter memory
  footprint, and additional API tests (rate limiting, file serving, real-stack upload limits,
  migrations).
- Repository hygiene for publication: portable `make install` (`PYTHON` override), CI concurrency,
  timeouts and failure artifacts, `.nvmrc`/`.python-version`, badges, and clone instructions.

## v0.1.0 - 2026-07-17

Initial public portfolio release.

### Added

- Local PDF upload, structural validation, deterministic duplicate detection, page-by-page extraction,
  scanned-page feedback, overlapping chunks, sentence-transformer embeddings, and persistent Chroma
  storage.
- Conversation creation, renaming, history, document selection, document-scoped retrieval, streamed
  answers, fixed insufficient-evidence behavior, and application-owned page citations.
- Ollama and OpenAI-compatible providers with bounded requests, installed-model health checks, safe
  failures, and a deterministic test-only provider.
- Responsive React interface with document status, mutation feedback, dark mode, safe Markdown,
  source cards, and a PDF.js viewer that opens the cited page.
- SQLite/Alembic metadata, structured logging, environment validation, deterministic sample PDF,
  guarded local-data reset, architecture/security/development documentation, and contribution policy.
- Pytest, Vitest, Playwright, Ruff, mypy, ESLint, Prettier, BuildKit, Compose smoke checks, GitHub
  Actions, and Dependabot coverage.

### Fixed

- Made ingestion, retry, and deletion lifecycle claims atomic so stale requests cannot overwrite a
  competing transition.
- Revalidated vector matches against relational document, chunk, and page records before prompt or
  citation construction.
- Added retryable deletion tombstones and cleanup recovery across uploaded files, relational data,
  Chroma vectors, and interrupted ingestion.
- Isolated E2E ports from running development/Docker services and made sample generation byte-for-byte
  reproducible.
- Prevented frontend mutation races, preserved unsaved settings during query refreshes, and made
  conversation/document errors visible in empty states.
- Corrected production PDF.js worker MIME handling and container-to-host provider URL behavior.

### Security

- Enforced extension, MIME, PDF signature/structure, per-file, aggregate-byte, file-count, declared
  body, and chunked-body upload limits with randomized storage names.
- Limited retrieval to selected documents and constructed citation links only from revalidated
  application records.
- Filtered invented, numeric, parenthetical, incomplete, malformed, and internal `GROUNDING:` model
  citation syntax from streaming and persisted answers.
- Hardened provider response parsing, request-ID reflection, persisted-setting recovery, secret
  handling, and error translation.
- Added non-root, read-only Docker services with dropped capabilities, `no-new-privileges`, loopback
  port binding, bounded temporary filesystems, CPU-only PyTorch, and health checks.

### Documentation

- Added verified native and Docker setup, configuration reference, architecture/data-flow/security
  documentation, honest limitations, focused roadmap, release checklist, issue forms, pull-request
  template, security reporting policy, code of conduct, and production readiness self-audit results.

[0.2.0]: https://github.com/ewilmoth23/grounded-pdf/releases/tag/v0.2.0
