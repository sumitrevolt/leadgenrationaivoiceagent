# Local Render Environment — Findings & Constraints (T02 input)

**Date:** 2026-09-11 · **Verified by:** team lead (read-only probes) · **Status:** RESEARCH
**Why:** T02 (local render worker ↔ VPS data plane) assumes a local render box. These are the
measured facts about this machine, and one **owner action** is required before T02 can render.

---

## 1. Measured environment

| Probe | Result | Evidence label |
|---|---|---|
| Docker available | **Yes** — Docker Desktop `29.7.2` (build a7dcaa6) | PRODUCTION-PROVEN (local) |
| Docker engine OS | **linux** (`OSType=linux`) → Linux containers, so Linux-only primitives are usable | PRODUCTION-PROVEN (local) |
| **Docker VM memory** | **4,107,522,048 bytes ≈ 3.83 GB total** | PRODUCTION-PROVEN (local) |
| `unshare` on the Windows host | **NOT FOUND** (expected — it is a Linux util-linux binary) | PRODUCTION-PROVEN (local) |

## 2. The renderer is headless Chrome, not a native toolchain

`Dockerfile.video` derives from the app image and **only adds the HyperFrames render toolchain —
Node + a pinned Chrome headless shell + pinned npm packages**. The file's own comment states the
toolchain is a separate image because *"Chromium plus its shared libraries is several hundred MB,
and the web container has no reason to carry a browser."*

The service that runs it:

```yaml
# docker-compose.vps.yml:435-443
worker-video:
  mem_limit: 2000m
  mem_reservation: 512m
  cpus: "1.5"
  command: celery -A app.worker worker -Q video --loglevel=info --concurrency=1
```

The video overlay lives at **`deploy/compose/docker-compose.video.yml`** (the root-level
`docker-compose.video.yml` is empty). It sets **`shm_size: 512m`** at line 50 — so the classic
headless-Chrome `/dev/shm` crash is already handled in that overlay.

---

## 3. Findings that change T02

**F1 — RC5 network isolation IS achievable, but only inside the container.**
`unshare` is absent on the Windows host, but Docker runs **Linux** containers. So
`network_guard.build_isolation()` can return `method="netns"` / `enforced=True` **when the render
executes inside the Linux container**. If the render is ever launched on the bare Windows host, it
falls back to `method="proxy_blackhole"` / `enforced=False` and the artifact must be labelled
`network_best_effort` — never "hermetic". **The design's assumption holds; it just requires the
container path, not a host path.**

**F2 — ⚠️ MEMORY IS THE REAL BLOCKER. OWNER ACTION REQUIRED.**
The Docker VM has **≈3.83 GB total**. `worker-video` alone requests `mem_limit: 2000m` plus
`shm_size: 512m`, and headless Chrome's real footprint sits well above its nominal limit. Add Docker
Desktop's own overhead and there is very little headroom. Renders will OOM or thrash on the current
allocation.

**Owner action:** raise Docker Desktop's memory allocation (Settings → Resources → Memory) before
T02 is switched on. Suggested floor: **8 GB**, given a 2 GB render limit + 512 MB shm + Chrome
peak + the data-plane worker. This machine has 16 GB total, so 8 GB is feasible but should be
confirmed against what else the owner runs.

**F3 — `shm_size: 512m` exists only in the overlay, not the base compose file.**
If anyone runs the renderer without `deploy/compose/docker-compose.video.yml`, headless Chrome gets
Docker's default 64 MB `/dev/shm` and will crash unpredictably. T02 should either fail closed when
shm is too small, or record the effective shm size in the render evidence so a crash is diagnosable
rather than mysterious.

**F4 — `--concurrency=1` on the video queue is deliberate and should stay.**
`worker-video` is pinned to concurrency 1. With 2 GB limit / 1.5 CPUs, parallel Chrome instances
would contend for both. T02's local render worker must therefore be **serial per box**, which makes
the lease/heartbeat design in T02 load-bearing rather than optional — one slow render blocks the
queue, so lease TTL and reclaim behaviour matter.

**F5 — the local box is a laptop, not a server.** Nothing here proves the machine is always on.
This is open item **OI-1** and it directly determines whether T02's pull+lease model tolerates sleep
(the design already assumes it does). Still needs the owner's answer.

---

## 4. Summary for the owner

| Item | Status |
|---|---|
| Can the local render work at all? | **Yes** — Docker Desktop runs Linux containers and the renderer image already exists |
| Can RC5 be genuinely enforced (`enforced=True`)? | **Yes** — inside the container (`unshare` exists there), not on the Windows host |
| Is `/dev/shm` handled? | **Yes** — `shm_size: 512m` in `deploy/compose/docker-compose.video.yml:50` |
| **Is there enough memory today?** | **NO — 3.83 GB total vs a 2 GB render limit + 512 MB shm + Chrome peak.** Owner must raise Docker Desktop memory (~8 GB suggested) |
| Is the box always on? | **UNKNOWN** — OI-1, owner must confirm |

---

*Evidence vocabulary: PRODUCTION-PROVEN · CODE-PRESENT · TEST-PROVEN · LOCAL-ONLY · PARTIAL · STALE · UNKNOWN.*
*All probes were read-only. No files were modified and nothing was started or deployed.*
