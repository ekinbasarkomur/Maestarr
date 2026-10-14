# Maestarr — one image: the web UI is built in a Node stage and served by the
# Python app. Nothing runs on Node at runtime.

# --- UI ---------------------------------------------------------------------
FROM node:22-alpine AS ui
WORKDIR /src/ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ui/ ./
# vite.config.ts writes the build to ../maestarr/web
RUN mkdir -p /src/maestarr && npm run build

# --- App --------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MAESTARR_HOST=0.0.0.0 \
    MAESTARR_PORT=8709 \
    MAESTARR_DATA_DIR=/data \
    MAESTARR_LOG_DIR=/data/logs

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Dependencies first, in their own layer: a code change only reinstalls
# Maestarr itself, not the whole dependency tree.
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p maestarr && touch maestarr/__init__.py \
    && pip install --no-cache-dir . \
    && pip uninstall -y maestarr \
    && rm -rf maestarr build
COPY maestarr/ ./maestarr/
COPY --from=ui /src/maestarr/web ./maestarr/web
RUN pip install --no-cache-dir --no-deps .

RUN useradd --create-home --uid 10001 maestarr \
    && mkdir -p /data/logs \
    && chown -R maestarr:maestarr /data
USER maestarr
VOLUME ["/data"]
EXPOSE 8709

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8709/health || exit 1

CMD ["maestarr", "serve"]
