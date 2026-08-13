FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ src/

RUN /opt/venv/bin/pip install --no-compile ".[server,online]"


FROM python:3.11-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 code-navi \
    && useradd --system --uid 10001 --gid code-navi --no-create-home code-navi \
    && mkdir -p /workspace /data/runs \
    && chown -R code-navi:code-navi /workspace /data

COPY --from=builder /opt/venv /opt/venv
COPY migrations/ /opt/code-navi/migrations/
COPY alembic.ini /opt/code-navi/alembic.ini

USER code-navi
WORKDIR /workspace

ENTRYPOINT ["code-navi"]
CMD ["shell", "--project", "/workspace", "--events-dir", "/data/runs"]
