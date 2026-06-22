# Docker Compose & Dockerfile Guide

Quick map of the compose/Dockerfile files in the repo root (verify against your VPS before relying on any one).

## Compose files
| File | Purpose | When used |
|---|---|---|
| docker-compose.vps.yml | **Canonical production** — app + Postgres + Redis (+ worker/beat via `--profile celery`) | Live VPS (`/opt/leadgen`) |
| docker-compose.observability.yml | Prometheus + Grafana + Alertmanager + Loki + Tempo + Uptime Kuma + Gatus | Opt-in monitoring stack |
| docker-compose.tools.yml | Self-hosted SearXNG + ntfy + changedetection.io | Opt-in tools |
| docker-compose.staging.yml | Staging (separate DB+Redis, port 8001, automation OFF) | Pre-prod testing |
| docker-compose.ollama.yml | Local Ollama LLM | Optional local-LLM experiments |
| docker-compose.prod.yml | Likely legacy (Cloud-Run-era). **Verify / consider removing** if superseded by vps.yml | — |
| docker-compose.yml | Base/dev default | Local dev |

## Dockerfiles
| File | Purpose |
|---|---|
| Dockerfile.lock | **Canonical** — builds from committed requirements.lock.txt (`--no-deps`, py3.12); bakes ML assets | 
| Dockerfile | Generic/base build |
| Dockerfile.production | Verify vs Dockerfile.lock; consolidate if redundant |

## Recommendation
Keep vps.yml + observability.yml + tools.yml + staging.yml as the active set. Audit prod.yml, docker-compose.yml, and Dockerfile/Dockerfile.production for redundancy with the canonical vps.yml/Dockerfile.lock and remove what's stale (one at a time, verify deploy after each).
