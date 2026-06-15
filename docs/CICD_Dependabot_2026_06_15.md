# SaaS-Infra Upgrade — CI/CD Quality Gate + Dependabot

**Date:** 2026-06-15 · **Scope:** SaaS-blueprint deep-dive + top SaaS-infra staples; close the genuine gap (no CI/CD).
**Outcome:** GitHub Actions CI gate (`.github/workflows/ci.yml`) + Dependabot (`.github/dependabot.yml`). YAML validated. **GitHub-side only — VPS untouched.**

---

## 1. Research — SaaS-blueprint + staples

- **tuliosousapro/SaaS-blueprint (BRAINIAC)** = ek **business playbook library** (80+ PLAYBOOK.md: idea→validation→…→scaling + AI skills: changelog/conventional-commits/semver/git-control). Code/infra repo NAHI. Iska sirf **infra-relevant pillar = "Infrastructure → Cloud Hosting, DevOps, CI/CD, Monitoring, Security."** (Tere paas hosting/monitoring/security already hai — CI/CD missing tha.)
- **Top SaaS-infra staples (2026 research):** multi-tenant isolation ✓ (tenant middleware), RBAC ✓ (team-access), audit logs ✓ (agent_events/consent_ledger), observability ✓ (+ naye exporters), payments ✓, rate-limit ✓, secrets ✓ (SOPS) — aur **CI/CD + supply-chain security** = jo missing tha.

## 2. Gap (proven)

`.github/` **bilkul khaali** — koi CI workflow nahi, koi Dependabot nahi. Aaj ka only gate = **manual** `run_tests.bat` deploy se pehle. Matlab broken code main pe push ho sakta hai bina kisi automated check ke. SaaS-engineering ka core staple missing tha.

(pyproject me already ruff + pre-commit + pytest configured — aur `network` marker pe note: *"CI: -m 'not network'"* — yani CI ke liye design tha, bas workflow nahi tha.)

## 3. Fix

### `.github/workflows/ci.yml` — har push/PR pe automated gate
- **`quality` job** (fast, dep-light, reliable): `compileall` (syntax, must-pass) + `check_secrets.py` (must-pass) + `ruff check` (informational annotations — pre-existing style-debt block na kare).
- **`tests` job**: deps install **Dockerfile.lock-mirror** (lock `--no-deps` + torch CPU index) → `prod_check.py` → `pytest -m "not network"` (LLM/internet tests skip — repo marker, no API keys CI me).
- `concurrency` (superseded runs cancel), `paths-ignore` (docs-only push pe heavy CI nahi), `permissions: contents:read` (least-privilege).

### `.github/dependabot.yml` — supply-chain security automation
- Weekly PRs: **pip** (vulnerable/outdated deps, minor+patch grouped), **github-actions** (action versions), **docker** (Dockerfile base-image CVEs). Auto-merge OFF (review-then-merge).

## 4. Discipline
- SaaS-blueprint ke playbooks/skills (changelog/semver/git-control) **add nahi kiye** — tere paas already 241 skills + slash-commands + memory hai (duplicate).
- Auto-DEPLOY from CI **nahi** banaya — tera VPS deploy deliberately manual hai (git-pull + docker, full control). CI sirf **pre-merge quality gate** hai, deploy nahi (right separation).
- Heavy full-pytest CI ko reliable rakha (`not network` + lock-mirror); quality-job dep-light = hamesha green-able.

## 5. Verify + activate
- YAML validated: CI 2 jobs (quality/tests), Dependabot 3 ecosystems.
- **Activation = sirf commit+push** (GitHub Actions us push pe khud chal jayega; Dependabot enable ho jayega). **VPS pe kuch nahi** — ye purely GitHub-side hai.
- **First run note:** `quality` job reliably green hoga. `tests` job pehli baar runner pe dep-install validate karega — agar koi dep tweak chahiye to Actions-log me exact dikhega (normal CI bring-up, 1-line fix). Green hone ke baad branch-protection me "required check" bana sakte (PRs ko gate karne ke liye).

### Files
- `.github/workflows/ci.yml` · `.github/dependabot.yml`

## Sources
- SaaS-blueprint (BRAINIAC) — https://github.com/tuliosousapro/SaaS-blueprint
- Multi-tenant SaaS production guide (audit logs, CI/CD, observability) — https://northflank.com/blog/multi-tenant-saas-platform-deployment
- IaC + CI/CD best practices — https://www.harness.io/harness-devops-academy/infrastructure-as-code-best-practices
- GitHub Actions Python CI — https://docs.github.com/en/actions/automating-builds-and-tests/building-and-testing-python
