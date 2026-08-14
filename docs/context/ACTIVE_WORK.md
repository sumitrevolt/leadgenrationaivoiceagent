# ACTIVE_WORK - max 3 workstreams

---

## WS-DSH DeepSeek Harness full migration (CURSOR LANE B)
- **ID:** WS-DSH
- **Business outcome:** Replace only the governed planning/turn/tool loop through a reversible, evidence-gated DSH path without introducing a second control plane or touching voice
- **Current state:** **CODE-READY/INERT, integration in progress** · source-built pair is bit-identical; fake MCP/model smoke, lifecycle bounds, closure proof and CycloneDX SBOM green · `DSH_RUNTIME_ENABLED=0`, `DSH_SHADOW_ENABLED=0`, allowlist empty
- **Prep completed:** Hardened Cordis closure, pkg-visible config path, Linux fake MCP/model lifecycle smoke, reproducibility proof, CycloneDX SBOM, shadow evidence gate and rollback contract
- **Next exact action:** Merge/deploy code only under the user's current authorization; do not arm runtime/shadow, promote canaries, or retire legacy paths without separate owner authorization.
- **Out of scope:** Any deploy/flag arm/promotion/deletion without owner authorization · plan-file edits · stock wheel/direct embedding/default tools/direct provider access · voice migration

---

## WS-GTM1 Hot Queue → 2nd paid (CURSOR LANE B)
- **ID:** WS-GTM1
- **Business outcome:** 2nd paying Marketing customer this week via Hot Queue outreach execution
- **Current state:** Technical READY · CODE-PRESENT this session: admin/inbox/marketing "Aaj" path Hot Queue pe; owner outreach + UPI confirm still the revenue gate · Evidence `docs/evidence/REVENUE_READY_20260812.md` + live 2026-08-14 `ready_for_first_paid_customer=true`
- **Next exact action:** Owner daily Hot Queue blitz (15 min/day at `/app/inbox`) + UPI approval when payment arrives
- **Out of scope:** Deploy · flag arm · lead magnet traffic generation

---

## WS-SEC Security/compliance residual (CURSOR LANE B)
- **ID:** WS-SEC
- **Business outcome:** All compliance gates (DND/TRAI/DPDP/secrets) remain fail-closed while voice stays frozen
- **Current state:** Gates INTACT · voice/Swara surface remains frozen · no compliance gate touched by WS-DSH
- **Next exact action:** Monitor only; no voice edits and no gate weakening
- **Out of scope:** Voice/Swara edits · weakening compliance gates

---

## Parked (not in active 3)
- **WS-UPI304** Guest bind workflow is parked on external wait for first live proof; no code change in this DSH slice
- **WS-HYG** Duplicate/docs hygiene 2026-08-14 — archived + AUTH-DEPLOYED on `150bf898` via PR #356. COMPLETE.
- **WS-DSH180** ADR-180 SessionEvent steal remains LIVE-INERT on prod `150bf898` (`HARNESS_SESSION_EVENTS` UNSET). Do not arm.
- **WS-GOV** Boss + Second Brain governance (PR #330 MERGED `8f5a2e2d`, prod has ancestry, flag OFF)
- **WS-BUZZ** Local Buzz Desktop + relay (Cursor ACP Boss canonical `1b13cecc`, relay verified)
- **WS-DEP329** Rollback retention lineage
- **WS-REV** #306 live proofs (after #304 guest bind proven)
- **WS-AMAX** DUNNING safe-enabler (#307 stays OFF per owner decision)
- **WS-SEC1** Vobiz credential rotation
- Creative OS expansion · Swara/voice (FROZEN) · Stage B AMBER OpenClaw
