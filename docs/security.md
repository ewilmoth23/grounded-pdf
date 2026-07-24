# Security and privacy

## Deployment assumption

Version 1 is intended for one trusted user on a local workstation or a trusted private network. It has
no authentication, authorization, tenant isolation, CSRF tokens, TLS termination, or hardened multi-
user job isolation. Local software is not automatically secure: **never expose the API or web ports
directly to the public internet**. Put authentication, TLS, strict network controls, and an application
security review in front of any remote deployment.

## Threat model

GroundedPDF defends against accidental or malicious uploaded filenames, non-PDF content disguised as
PDF, oversized uploads, corrupt/encrypted files, path traversal, model-produced HTML, model attempts to
invent source metadata, broad browser origins, and sensitive prompt logging. It does not defend against
a user with local filesystem access, a compromised model or embedding package, hostile PDFs exploiting
an unknown PyMuPDF/PDF.js vulnerability, traffic observation on an unencrypted LAN, or denial of
service by an already trusted local user.

## Upload protections

- The API enforces both `.pdf` extension and `%PDF-` signature, then asks PyMuPDF to open and load it.
- Per-file byte counts are enforced while streaming to disk; partial files are removed on failure.
- Display names are reduced to a basename and sanitized. Storage names are UUIDs.
- Every file path is resolved and required to be a direct child of the configured upload directory.
- Password-protected, corrupt, empty, and unsupported files receive specific safe errors.
- Multiple-file requests have configurable file-count and aggregate byte limits enforced by both the
  API and production reverse proxy. Normal requests are rate-limited per client IP.

MIME headers alone are not trusted. Antivirus or content-disarm scanning is outside the local version 1
scope and should be added before accepting documents from untrusted external users.

Interactive API documentation (`/docs`, `/redoc`) and the `/openapi.json` schema are served only when
`GROUNDEDPDF_ENVIRONMENT` is not `production`; the Docker stack runs in production mode and does not
expose them.

## Model and content safety

PDF text is untrusted content. The system prompt tells the provider not to follow instructions inside
sources. Retrieved context is not logged. The browser uses `react-markdown` with raw HTML disabled;
links and source cards are application components. The API, not the language model, creates structured
citation metadata from retrieved vectors.

Prompt injection can still influence local model phrasing. Users must verify important claims in the
cited source page. GroundedPDF is not a safety boundary for executing model output and exposes no agent
tools to the provider.

## Data storage and deletion

SQLite, Chroma, and uploaded PDFs live beneath `GROUNDEDPDF_DATA_DIR` by default. File permissions are
those of the operating-system account or non-root container user. Docker uses one named volume. Backups
of that directory contain private source material and conversation history and must be protected.

Deletion commits a retryable tombstone, removes vector records and the stored PDF, and then removes
the document row; foreign-key cascades remove pages, chunks, processing jobs, and conversation
selections. Citation rows persist as snapshots (document name, page number, excerpt) with their
document reference set to NULL so conversation history stays verifiable; deleting the conversation
removes them. Copies in filesystem backups, container snapshots, OS caches, or model-server logs
are not controlled by the application.

## Secrets and logging

API keys are accepted only through environment configuration. The safe settings endpoint never returns
them. `.env` is ignored by Git. Structured logs include operation names, generated IDs, counts, timings,
and safe errors, but never full document text, retrieved context, prompts, API keys, or answer bodies.
Review third-party model-server logging separately.

## Network controls

CORS defaults to the development and packaged web origins, credentials are disabled, and allowed
methods/headers are explicit. CORS is not authentication and does not prevent direct API requests.
Responses add request IDs, `nosniff`, and a restrictive referrer policy. The production web container
adds a content security policy, denies framing, and disables browser camera, location, and microphone
features.

Compose publishes only loopback ports. Both services run without root privileges, drop Linux
capabilities, forbid privilege escalation, and use read-only root filesystems with bounded temporary
filesystems. Application data and the embedding cache are the only persistent writable state. These
controls reduce accidental exposure; they do not turn the unauthenticated local application into a
safe public service.

## Reporting vulnerabilities

Do not report vulnerabilities in public issues, and never include private documents, tokens, or
exploit payloads containing real data. Use GitHub's private vulnerability reporting as described in
the repository [security policy](../SECURITY.md).
