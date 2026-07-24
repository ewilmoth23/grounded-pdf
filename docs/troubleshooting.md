# Troubleshooting

## Ollama is unavailable

Confirm `ollama serve` is running, then run `ollama list`. Pull the configured model if missing:

```bash
ollama pull llama3.2:3b
curl http://localhost:11434/api/tags
```

For Docker, the default API URL is `http://host.docker.internal:11434`. Override it with
`GROUNDEDPDF_DOCKER_OLLAMA_BASE_URL`; `GROUNDEDPDF_OLLAMA_BASE_URL` is the native-development URL and
is intentionally not reused inside the container. On Linux, use a current Docker Engine that supports
the configured host-gateway mapping. A remote Ollama server may need `OLLAMA_HOST=0.0.0.0:11434`;
expose it only on a trusted network.

## Embedding download fails

The sentence-transformer downloads on first document processing. Check network access, free disk
space, proxy/certificate configuration, and the model name. Docker stores this cache beneath
`/data/huggingface` in the named volume so recreating the container does not download it again. A
failed document can be retried after fixing the download. Tests use deterministic embeddings and do
not download a model.

## A PDF fails processing

Open the status error on Documents. Password-protected and corrupt files are rejected. Image-only pages
are recorded as non-searchable, and a document with no searchable text fails instead of pretending to
be indexed. To enable OCR, install the Tesseract executable and run
`.venv/bin/pip install -e "./apps/api[ocr]"`, set `GROUNDEDPDF_ENABLE_OCR=true`, and restart the API.
The standard Docker image does not include Tesseract. Re-export unusual PDFs through a trusted PDF
tool when OCR is not desired.

## Browser reports a CORS error

Add the exact scheme, host, and port to the JSON list in `GROUNDEDPDF_CORS_ORIGINS`, then restart the
API. Do not use `*` when a specific origin works. Confirm `VITE_API_BASE_URL` points to the same API.

## Port 5173, 8000, or 8080 is busy

Stop the conflicting process or start Vite/Uvicorn on another port and update CORS/API URL together.
For Docker, change only the host side, for example `"8081:8080"`.

## Docker data or permissions

Inspect `docker compose logs api` and `docker volume inspect grounded-pdf_groundedpdf_data`. The API
runs as a non-root user; bind mounts must be writable by that user. `docker compose down` preserves the
named volume. Removing the volume permanently deletes database, PDF, and vector data.

Run `make docker-verify` for a complete build/start/proxy smoke test. If the build attempts to download
CUDA packages, confirm the current API Dockerfile still installs PyTorch from the official CPU wheel
index before installing GroundedPDF.

## Migration fails

Back up the data directory, verify `GROUNDEDPDF_DATABASE_URL`, and run from `apps/api`:

```bash
alembic current
alembic history
alembic upgrade head
```

Do not delete a production database to bypass a migration error. If a development database is
disposable, use the interactive `make reset-data`, then rerun migrations.

## Model request times out

Small local models can be slow on first load. Verify the model responds directly, close memory-heavy
processes, and raise `GROUNDEDPDF_MODEL_TIMEOUT_SECONDS` up to 600. Reduce the chat model size or output
token limit when hardware is constrained.

## Answer says evidence is insufficient

Confirm the document is `ready`, selected in the current conversation, and contains extractable text.
Ask a more specific question using the document's terminology. Lowering the retrieval threshold can
increase irrelevant evidence and is not the first fix. Open the PDF to verify the fact is actually
present.

## Vector store or database is unavailable

Check data-directory permissions and free disk space. Do not manually edit Chroma files while the API
is running. Preserve SQLite and Chroma together in backups; rebuilding vectors requires reprocessing
every source PDF.
