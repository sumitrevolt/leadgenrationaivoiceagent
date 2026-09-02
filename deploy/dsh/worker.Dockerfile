# syntax=docker/dockerfile:1.7

ARG DSH_IMAGE=leadgen-dsh:47f94385
ARG PYTHON_IMAGE=python:3.12.11-slim-bookworm@sha256:c00fc7b44d844b6da22861ec24af43968a5200eac4ec607b4725d585165d6b49

FROM ${DSH_IMAGE} AS dsh-runtime

FROM ${PYTHON_IMAGE} AS python-deps
WORKDIR /build
COPY requirements-dsh.lock.txt .
RUN python -m pip install \
      --disable-pip-version-check \
      --no-cache-dir \
      --no-deps \
      --target /install \
      -r requirements-dsh.lock.txt

FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY --from=python-deps --chown=65532:65532 /install /usr/local/lib/python3.12/site-packages
COPY --chown=65532:65532 app /app/app
COPY --from=dsh-runtime --chown=65532:65532 --chmod=0555 /usr/local/bin/dsh-jsonrpc-agent /usr/local/bin/dsh-jsonrpc-agent
COPY --from=dsh-runtime --chown=65532:65532 --chmod=0444 /usr/local/bin/cordis.yml /usr/local/bin/cordis.yml
COPY --from=dsh-runtime --chown=65532:65532 --chmod=0444 /usr/share/dsh/runtime-proof.json /usr/share/dsh/runtime-proof.json
COPY --from=dsh-runtime --chown=65532:65532 --chmod=0444 /usr/share/licenses/dsh/UPSTREAM_LICENSE /usr/share/licenses/dsh/UPSTREAM_LICENSE

ENV DSH_CORDIS_CONFIG=/usr/local/bin/cordis.yml \
    HOME=/tmp
USER 65532:65532
WORKDIR /app
ENTRYPOINT ["python", "-m", "celery", "-A", "app.dsh_worker:celery_app", "worker", "--queues", "dsh", "--concurrency", "1", "--prefetch-multiplier", "1", "--max-tasks-per-child", "1", "--loglevel", "INFO"]
