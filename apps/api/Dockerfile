# syntax=docker/dockerfile:1
FROM python:3.14-slim AS runtime

ARG TORCH_VERSION=2.13.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    HF_HOME=/data/huggingface \
    XDG_CACHE_HOME=/data/cache

RUN groupadd --system groundedpdf \
    && useradd --system --gid groundedpdf --create-home groundedpdf

WORKDIR /app
COPY pyproject.toml requirements.runtime.txt ./
# PyPI's Linux torch wheel can resolve a multi-gigabyte CUDA stack. GroundedPDF is
# CPU-only, so install the matching wheel from PyTorch's official CPU index first.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url https://download.pytorch.org/whl/cpu "torch==${TORCH_VERSION}" \
    && pip install --requirement requirements.runtime.txt

COPY README.md alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-deps .

RUN mkdir -p /data/uploads /data/chroma /data/huggingface /data/cache \
    && chown -R groundedpdf:groundedpdf /data /app
USER groundedpdf

EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).read()"]

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
