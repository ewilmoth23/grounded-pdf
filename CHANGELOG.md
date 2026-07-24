# Changelog

All notable changes to GroundedPDF are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use semantic versioning.

## Unreleased

### Fixed

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

[0.1.0]: https://github.com/ewilmoth23/grounded-pdf/releases/tag/v0.1.0
