# Contributing to GroundedPDF

Thank you for improving verifiable, local document research. By participating, you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Before starting

Search existing issues and discuss large architecture or behavior changes before implementation. Do
not attach private PDFs, credentials, proprietary model output, or personal data to an issue or test.

## Development workflow

1. Fork and branch from `main`.
2. Use a descriptive branch such as `feat/citation-highlighting`, `fix/encrypted-pdf-error`,
   `docs/ollama-linux`, or `test/deletion-cleanup`.
3. Follow [docs/development.md](docs/development.md) for setup.
4. Keep commits focused and use imperative commit subjects.
5. Add meaningful tests for behavior and failure paths.
6. Run `make test`, `make lint`, and `make build` before opening a pull request. Run the Playwright
   flow for cross-boundary changes and `make docker-verify` for packaging/runtime changes.

## Engineering standards

- Preserve 1-based page numbers across all boundaries.
- Never make the model the authority for citation metadata.
- Never broaden retrieval beyond the conversation's selected documents.
- Keep uploaded filenames out of storage paths and secrets out of browser responses/logs.
- Prefer a small explicit module over a framework or abstraction without a current use.
- Update configuration tables, examples, migrations, and architecture documentation with code changes.
- Do not add required paid services or features outside the version 1 boundaries in the README.

Tests should assert outcomes, not implementation trivia. Backend tests must use temporary data and must
not require Ollama or network access. Frontend tests should exercise accessibility roles and typed API
states. Add Playwright coverage only for high-value cross-boundary behavior.

## Pull-request standard

Complete the pull-request template, link the issue, explain user-visible and architectural effects,
list the exact commands run, and call out migrations or data compatibility. CI must pass with no new
lint warnings. Reviewers may request source-viewer screenshots for visual changes.

Screenshots must come from the working application and use the generated synthetic PDF or other
clearly public content. Do not submit mockups as evidence that implementation behavior works.

Small corrections are welcome. A pull request may be declined when it weakens grounding, privacy,
installation simplicity, or the local single-user focus.

## Security reports

Follow [SECURITY.md](SECURITY.md) and use GitHub's private vulnerability-reporting workflow. Do not
publish exploit details or real sensitive data in an issue or pull request.
