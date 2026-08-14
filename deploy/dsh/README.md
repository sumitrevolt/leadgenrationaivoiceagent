# Hardened DeepSeek Harness runtime

This directory defines the only supported DSH carrier for LeadGen: a pinned,
source-built Linux x64 executable in a non-root distroless image. The upstream
wheel, default Cordis composition, and direct provider adapters are not used.

Security boundary:

- one process per governed run;
- only `DSH_RUN_TOKEN`, `DSH_MCP_URL`, and `DSH_LLM_BASE_URL` enter the child;
- only the internal streamable-HTTP MCP gateway and free-AI proxy are reachable;
- no Bash, filesystem mutation, jobs, browser, subagent, scheduler, skills,
  workspace discovery, telemetry, or direct-provider package in the closure;
- no package/model download at image startup;
- production remains inert while `DSH_RUNTIME_ENABLED=0`.

Canonical Linux build:

```bash
docker build \
  --file deploy/dsh/Dockerfile \
  --tag leadgen-dsh:47f94385 \
  .
```

Windows development must use Docker Desktop's Linux engine or WSL2. A native
Windows artifact is intentionally unsupported. If Docker's Linux engine is not
available, run static verification only:

```powershell
python scripts/verify_dsh_supply_chain.py
python -m pytest tests/test_dsh_supply_chain.py -q
```

The build emits `/usr/share/dsh/runtime-proof.json` and `SHA256SUMS`. CI also
generates an SBOM from the final image and runs fake-MCP/fake-model lifecycle
tests. Any closure, licence, smoke, shutdown, or cancellation failure blocks
shadow rollout.

`@yao-pkg/pkg` writes a random six-character `pkg-sea-*` temporary-directory
suffix into otherwise identical executables. The build replaces exactly one
equal-length diagnostic suffix with `pkg-sea-dsh000` and fails closed if the
upstream carrier layout changes. CI extracts both executables and independently
hashes them; `BIT_FOR_BIT_REPRODUCIBLE` is emitted only when both artifact
hashes and both closure proofs match.
