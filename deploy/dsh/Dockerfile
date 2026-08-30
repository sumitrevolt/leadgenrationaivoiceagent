# syntax=docker/dockerfile:1.7

ARG NODE_IMAGE=node:24.9.0-bookworm@sha256:86a81e1721186f2c5c313657496a84ac776509e265ab7677252e412b366a2b87
ARG RUNTIME_IMAGE=gcr.io/distroless/cc-debian12:nonroot@sha256:9a5775272c79c226db4d6762d3b5a2caffb2b9a59dcbe5ce8dc8879c9c404115

FROM ${NODE_IMAGE} AS builder

ARG DSH_REPOSITORY=https://github.com/deepseek-ai/deepseek-harness.git
ARG DSH_COMMIT=cd5ef8148158c3a752a658978873241fdf8e2bbc
ARG DSH_TREE=a712eec535b48badc4fefb4df5176a7002e4280b
ARG DSH_ARCHIVE_SHA256=1fe7d2380d3e53eac2f6ee92ee5c81850ddc9b735b5910bae132cf1fc12b7211
ARG PNPM_VERSION=11.7.0
ARG SOURCE_DATE_EPOCH=1787849863

ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH} \
    TZ=UTC \
    PNPM_HOME=/pnpm \
    PATH=/pnpm:${PATH}

WORKDIR /src

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# hadolint ignore=SC1083
RUN git init . \
    && git remote add origin "${DSH_REPOSITORY}" \
    && git fetch --depth=1 origin "${DSH_COMMIT}" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "${DSH_COMMIT}" \
    && test "$(git rev-parse HEAD^{tree})" = "${DSH_TREE}" \
    && test "$(git archive --format=tar HEAD | sha256sum | cut -d' ' -f1)" = "${DSH_ARCHIVE_SHA256}"

# Install exactly the upstream lock before applying the local source hardening
# and dependency-subset manifest. The final closure is independently scanned.
RUN --mount=type=cache,id=leadgen-dsh-pnpm-store,target=/pnpm/store,sharing=locked \
    corepack enable \
    && corepack prepare "pnpm@${PNPM_VERSION}" --activate \
    && test "$(pnpm --version)" = "${PNPM_VERSION}" \
    && pnpm config set store-dir /pnpm/store \
    && pnpm install --frozen-lockfile --ignore-scripts \
      --fetch-retries=5 \
      --fetch-retry-mintimeout=20000 \
      --fetch-retry-maxtimeout=120000 \
      --fetch-timeout=300000 \
      --network-concurrency=16

COPY deploy/dsh/hardening.patch /policy/hardening.patch
COPY deploy/dsh/runtime.package.json /policy/runtime.package.json
COPY deploy/dsh/cordis.yml /policy/cordis.yml

RUN git apply --check --ignore-whitespace /policy/hardening.patch \
    && git apply --ignore-whitespace /policy/hardening.patch \
    && cp /policy/runtime.package.json python/sdk-runtime/package.json \
    && cp /policy/cordis.yml python/sdk-runtime/src/deepseek_harness_runtime/runtime/cordis.yml \
    && pnpm install --lockfile-only --ignore-scripts --no-frozen-lockfile --prefer-offline \
      --fetch-retries=5 \
      --fetch-retry-mintimeout=20000 \
      --fetch-retry-maxtimeout=120000 \
      --fetch-timeout=300000 \
      --network-concurrency=16 \
    && node --import tsx/esm scripts/verify-runtime-closure.ts \
    && node --import tsx/esm scripts/build-exe-for-python-sdk.ts --targets=node24-linux-x64

COPY deploy/dsh/verify_runtime.mjs /policy/verify_runtime.mjs

# @yao-pkg/pkg embeds its random mkdtemp suffix as diagnostic source metadata.
# Replace exactly that equal-length suffix; fail if pkg changes the carrier
# shape so two clean builds remain honestly bit-identical.
# hadolint ignore=SC2016
RUN node --input-type=module -e 'import { readFileSync, writeFileSync } from "node:fs"; const path = "dist-exe/dsh-jsonrpc-agent-pkg-linux-x64"; const data = readFileSync(path); const text = data.toString("latin1"); const matches = [...text.matchAll(/\/tmp\/pkg-sea-[A-Za-z0-9]{6}\/sea-main\.js/g)]; if (matches.length !== 1) throw new Error(`expected one pkg SEA temp path, found ${matches.length}`); const stable = Buffer.from("/tmp/pkg-sea-dsh000/sea-main.js", "latin1"); if (stable.length !== matches[0][0].length) throw new Error("pkg SEA replacement length changed"); stable.copy(data, matches[0].index); writeFileSync(path, data);' \
    && mkdir -p /out \
    && node /policy/verify_runtime.mjs \
      --root python/sdk-runtime/src/deepseek_harness_runtime/runtime/node \
      --cordis /policy/cordis.yml \
      --binary dist-exe/dsh-jsonrpc-agent-pkg-linux-x64 \
      --output /out/runtime-proof.json \
    && cp dist-exe/dsh-jsonrpc-agent-pkg-linux-x64 /out/dsh-jsonrpc-agent \
    && cp /policy/cordis.yml /out/cordis.yml \
    && cp LICENSE /out/UPSTREAM_LICENSE \
    && sha256sum /out/dsh-jsonrpc-agent /out/cordis.yml /out/runtime-proof.json > /out/SHA256SUMS

FROM ${RUNTIME_IMAGE} AS runtime

LABEL org.opencontainers.image.title="LeadGen hardened DeepSeek Harness runtime" \
      org.opencontainers.image.source="https://github.com/deepseek-ai/deepseek-harness" \
      org.opencontainers.image.revision="cd5ef8148158c3a752a658978873241fdf8e2bbc" \
      org.opencontainers.image.licenses="MIT"

COPY --from=builder --chown=65532:65532 --chmod=0555 /out/dsh-jsonrpc-agent /usr/local/bin/dsh-jsonrpc-agent
# pkg existsSync can see /usr/local/bin (binary dir) but not freshly-created
# /etc or /usr/local/etc trees from COPY in this distroless stage.
COPY --from=builder --chown=65532:65532 --chmod=0444 /out/cordis.yml /usr/local/bin/cordis.yml
COPY --from=builder --chown=65532:65532 --chmod=0444 /out/runtime-proof.json /usr/share/dsh/runtime-proof.json
COPY --from=builder --chown=65532:65532 --chmod=0444 /out/SHA256SUMS /usr/share/dsh/SHA256SUMS
COPY --from=builder --chown=65532:65532 --chmod=0444 /out/UPSTREAM_LICENSE /usr/share/licenses/dsh/UPSTREAM_LICENSE

# pkg SEA embeds a fake argv[1]; real args start at argv[2].
ENV DSH_CORDIS_CONFIG=/usr/local/bin/cordis.yml \
    HOME=/tmp
USER 65532:65532
WORKDIR /run/dsh
ENTRYPOINT ["/usr/local/bin/dsh-jsonrpc-agent"]
CMD ["/usr/local/bin/cordis.yml"]
