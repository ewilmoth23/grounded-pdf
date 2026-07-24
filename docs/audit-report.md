# Production readiness self-audit

> This is a self-conducted pre-release audit executed inside the development workspace. It is not a
> third-party review.

**Audit date:** 2026-07-17 (America/New_York)  
**Overall status:** **Conditional Pass**

GroundedPDF's implemented version 1 scope passes the executed local, migration, end-to-end, and
production Docker checks after the corrections in this report. The status remains conditional only
because this workspace has no Git metadata, the GitHub workflow has not run on GitHub, and no Python
package or container-image CVE service was used. Checks that were not executed are identified below.

## Actual repository structure

| Path               | Verified responsibility                                                                                                                                                                                       |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `apps/api`         | FastAPI transport, SQLAlchemy/Alembic metadata, secure storage, PDF extraction, chunking, embeddings, Chroma access, retrieval, model providers, grounding, background ingestion, and 67 passing pytest cases |
| `apps/web`         | React/Vite application, typed API/SSE client, PDF.js viewer, 20 passing Vitest cases, one passing Chromium E2E flow, and the Nginx production image                                                           |
| `docs`             | Architecture, data flow, security model, development, troubleshooting, and this audit                                                                                                                         |
| `scripts`          | Environment doctor, isolated E2E preparation, deterministic sample generation, and guarded data reset                                                                                                         |
| `sample_documents` | Synthetic three-page evaluation PDF specification and generated artifact                                                                                                                                      |
| `.github`          | Four valid workflow/configuration YAML files, Dependabot, issue templates, and pull-request template                                                                                                          |
| repository root    | Compose, Make targets, environment template, policies, license, changelog, and README                                                                                                                         |

Generated dependencies, build output, caches, databases, model data, uploaded files, `.env`, and the
generated PDF are ignored. No second or duplicate production application was found.

## Acceptance and claim verification

| Area                      | Result                        | Executed evidence                                                                                                                                                                                                                                                                                                                                                   |
| ------------------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Secure document upload    | Pass                          | Tests cover filename, extension, MIME, PDF signature/structure, per-file size, configurable file count, aggregate raw bytes, duplicate uploads, and declared/chunked oversized requests. A real PDF was uploaded through production Nginx.                                                                                                                          |
| Page-by-page extraction   | Pass                          | The live synthetic PDF produced three relational page records and three chunks; extraction tests passed.                                                                                                                                                                                                                                                            |
| Metadata continuity       | Pass                          | Document ID, name, one-based page number, page ID, chunk index, and extraction method survive extraction, relational storage, Chroma metadata, revalidated retrieval, citations, and page routing.                                                                                                                                                                  |
| Embeddings and vectors    | Pass                          | Live ingestion loaded the sentence-transformer on CPU, stored three Chroma vectors, retrieved them, and deletion returned the collection to zero.                                                                                                                                                                                                                   |
| Selected-document scope   | Pass                          | Chroma applies a document-ID filter, retrieval revalidates every match against selected relational records, and unit/E2E tests passed.                                                                                                                                                                                                                              |
| Citation ownership        | Pass                          | Source objects are built from revalidated retrieval records. Invented, numeric, parenthetical, incomplete, and internal `GROUNDING:` wrappers are filtered from streaming and persistence before an allowed canonical marker is emitted.                                                                                                                            |
| Insufficient evidence     | Pass                          | Live Docker returned the exact refusal for an unsupported lunar-colony question, with no source cards or provider generation.                                                                                                                                                                                                                                       |
| Complete deletion         | Pass                          | After deleting the audit conversation and document, all eight relevant relational tables, Chroma vectors, and uploaded files reported zero rows/items.                                                                                                                                                                                                              |
| Streaming                 | Pass                          | Live Ollama SSE showed locked mutation controls while active, emitted the answer incrementally, normalized the citation, completed, and persisted it. Stream parser and failure tests passed.                                                                                                                                                                       |
| Citation navigation       | Pass                          | The production browser opened `/view?page=2`, displayed `Cited page 2`, and rendered the actual page-2 text containing `37 percent`.                                                                                                                                                                                                                                |
| Provider failures         | Pass                          | Tests cover unreachable providers, missing models, declared error objects, malformed Ollama/OpenAI response shapes, timeouts, and unexpected stream failures without leaking provider internals.                                                                                                                                                                    |
| Docker                    | Pass                          | Both Dockerfiles passed BuildKit checks. Compose rebuilt both images, reached healthy state, passed reverse-proxy/API/PDF-worker/non-root smoke checks, and produced no runtime error logs.                                                                                                                                                                         |
| GitHub Actions definition | Static pass                   | All four GitHub YAML files parsed. Each CI command was executed locally or through the equivalent Docker/E2E path. Hosted execution remains unverified.                                                                                                                                                                                                             |
| README commands           | Pass with explicit exceptions | Active quality, migration, sample, doctor, E2E, and Docker paths were executed. Long-running development/log commands were exercised through E2E/Docker; optional OCR installation, destructive reset, alternate-provider examples, and `docker-down` were intentionally not run. `make install` was dry-run validated because dependencies were already installed. |

## Critical findings

No unresolved critical findings.

## High-priority findings

No unresolved high-priority findings. This audit found and corrected:

1. Document retry, ingestion, and deletion could overwrite one another after stale status reads. Each
   lifecycle claim is now a conditional atomic update, with regression coverage for lost races.
2. Multi-file uploads were advertised but production Nginx enforced only a per-request approximation
   of the per-file limit. The API now enforces file count plus aggregate raw bytes, an early ASGI body
   ceiling handles declared and chunked requests, Nginx uses the batch limit, and Docker bounds `/tmp`.
3. A real local model emitted an internal `(GROUNDING: ...)` wrapper. The stream and persisted-answer
   filters now reduce the wrapper to the exact application-owned database citation.
4. Provider adapters trusted nested JSON response shapes. Ollama and OpenAI-compatible streams now
   reject malformed structures as safe provider-unavailable failures.
5. Conversation/document mutations could race with streaming or repeated clicks, and some mutation
   errors disappeared when no conversation existed. Controls now lock consistently and failures stay
   visible; query refreshes no longer erase unsaved settings.
6. Invalid legacy settings rows could break settings, health, and worker startup. Effective settings
   now retain valid overrides and safely ignore invalid persisted values.
7. Hosted Linux backend/E2E jobs could resolve the large CUDA PyTorch dependency stack for a CPU-only
   application. Both jobs now preinstall the same CPU wheel used by the production API image.

## Medium-priority findings

Corrected:

- Unsafe client request IDs are no longer reflected into response headers.
- A repeated identical PDF in one multipart request no longer duplicates the response entry.
- The document picker, conversation controls, upload drop zone, retry, and deletion controls now
  prevent duplicate mutations while work is active.
- Docker upload limits, temporary-storage sizing, settings display, security documentation, CI, and
  changelog now describe the implemented behavior.

Remaining:

- The suite emits six upstream warnings: five PyMuPDF SWIG deprecation warnings and one FastAPI
  TestClient transition warning. They do not affect current behavior but should be revisited during
  dependency updates.
- The first embedding-model use contacts Hugging Face and can be rate-limited when unauthenticated;
  the downloaded model is then retained in the Docker data volume.
- No Python vulnerability database scan or external container-image scan was executed. `pip check`,
  the npm registry audit, lockfile integrity, CPU-wheel build, and Dependabot are in place, but these
  are not substitutes for those release scans.
- The workspace is not a Git repository, so history, tracked-file cleanliness, signed commits,
  branch protection, and a hosted GitHub Actions result could not be checked.

## Corrections completed

- Added atomic lifecycle claims for ingestion, retry, and deletion.
- Added configurable per-file, per-batch, file-count, ASGI body, Nginx, and Docker tmpfs limits.
- Hardened citation filtering, provider parsing, request IDs, and persisted-settings recovery.
- Fixed frontend mutation locks, error visibility, and unsaved-settings refresh behavior.
- Added regression tests for every correction above.
- Added CPU-only PyTorch installation to backend and E2E CI jobs.
- Updated README, security guidance, environment template, Compose, settings UI, changelog, and this
  report.
- Removed all audit-created application data and verified complete cascaded cleanup.

## Commands executed and exact results

```text
make lint test build
  Ruff: pass; Ruff format check: 59 files already formatted
  mypy: success, 46 source files
  ESLint: pass; Prettier: pass
  pytest: 67 passed, 6 upstream warnings in 1.69s
  Vitest: 5 files / 20 tests passed in 937ms
  TypeScript + Vite production build: pass; 1,988 modules; 441ms

pytest --cov=app --cov-report=term-missing --cov-fail-under=80
  67 passed, 6 warnings; 87.05% total coverage

npm run e2e
  Chromium: 1 passed in 5.5s (test body 3.5s)

Alembic clean upgrade -> downgrade base -> upgrade head
  pass
alembic check
  No new upgrade operations detected.

docker build --check ./apps/api
docker build --check ./apps/web
  pass; no warnings
docker compose config --quiet
make docker-verify
  both images rebuilt; both services healthy; web, proxied API, PDF worker MIME,
  and non-root API checks passed

Docker runtime probe
  API uid 999; torch 2.13.0+cpu; CUDA false
  Nginx client_max_body_size 201m; API /tmp tmpfs 256M
  final service logs: no application or Nginx errors

Live production browser
  secure upload: ready; 3 pages / 3 chunks / 3 vectors
  supported answer: 37 percent with canonical [groundedpdf-sample.pdf, p. 2]
  unsupported answer: exact insufficient-evidence response with zero sources
  citation link: correct document and page=2; actual page-2 text rendered
  mutation controls disabled during stream; browser console errors: 0

Post-deletion runtime probe
  documents, pages, chunks, jobs, selections, conversations, messages, citations: all 0
  Chroma vectors: 0; uploaded files: 0

npm audit --audit-level=high
  found 0 vulnerabilities
pip check
  No broken requirements found.

GitHub YAML parse / Markdown link / marker / embedded-secret scans
  4 YAML files parsed; 15 Markdown files checked; 0 missing local links;
  no unresolved production placeholders or embedded secret patterns

make doctor
  Python, Node, npm, API environment, web dependencies, environment template: OK
make sample (twice)
  identical SHA-256: badba4b3b3570c614547bfa90c476eddf56bf14b443add24d241f527538b4861
```

The placeholder/exception scan found only intentional constructs: the empty SQLAlchemy declarative
base, a test helper, Alembic's migration template, user-facing input placeholders, and broad
boundaries that clean up then re-raise, log, or translate errors. No fake production provider is
selectable outside the test environment.

## Remaining limitations

- GitHub Actions is statically validated and mirrored locally, not executed on GitHub.
- Python/container CVE services were not run; do not describe the images as vulnerability-free.
- Product limits remain: local single-user operation, no authentication or tenant isolation,
  optional OCR outside the standard image, page-level rather than phrase highlighting, and
  in-process background jobs.
- Real-model wording is nondeterministic even though retrieval records and citations are
  application-owned.

## Recommended next action

Initialize Git, review the first commit carefully, publish to a private GitHub repository, enable
private vulnerability reporting and branch protection, run a Python dependency and container image
scan, and require all four CI jobs. After the hosted checks pass, the repository is suitable for a
public portfolio release with its documented local single-user scope.
