# `maestarr serve` as a container.
#
# The CLI is NOT containerized — it stays a host-installed binary that dials
# this container over the published loopback port. One long-running server in
# Docker, many short-lived clients outside.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # The package is pip-installed into site-packages, so the default log
    # directory would be derived from a root-owned path. Pin logs to the
    # mounted volume instead — compose bind-mounts ./logs here.
    MAESTARR_LOG_DIR=/app/logs

# Build tools for any wheel without a prebuilt aarch64 artifact, plus curl for
# the healthcheck. Apt lists are dropped in the same layer so they do not ship.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency metadata first so this layer caches across source-only edits.
COPY pyproject.toml README.md ./
COPY maestarr/ ./maestarr/

# `pip install .`, NOT `-e`. An editable install inside an image points at a
# build-context path that is not the runtime layout, and breaks the moment the
# source is not bind-mounted.
RUN pip install --no-cache-dir .

# Non-root. Created after the install so it owns nothing it should not.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/logs \
    && chown -R app:app /app
USER app

EXPOSE 8709

# The failure this exists to catch: a container left bound to 127.0.0.1 starts,
# logs normally, and refuses every connection. Without a healthcheck that looks
# like a mystery; with one it is simply an unhealthy container.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8709/health || exit 1
# 0.0.0.0 inside the container; compose publishes it on the host's loopback only.
CMD ["maestarr", "serve", "--host", "0.0.0.0", "--port", "8709"]
