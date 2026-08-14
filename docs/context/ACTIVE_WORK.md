# ACTIVE_WORK - max 3 workstreams

---

## WS-DSH DeepSeek Harness full migration (CURSOR LANE B)
- **ID:** WS-DSH
- **Business outcome:** Replace only the governed planning/turn/tool loop through a reversible, evidence-gated DSH path without introducing a second control plane or touching voice
- **Current state:** **CODE-READY/INERT, LOCAL-ONLY** · ADR-181 contract + ADR-182 rollout/retirement policy present · rollout, rollback drill, and retirement checklist documented · `DSH_RUNTIME_ENABLED=0`, `DSH_SHADOW_ENABLED=0`, allowlist empty · no prod arm/deploy/canary promotion/legacy deletion
- **Prep completed:** Evidence-gated waves frozen as shadow → Kavya RO → Isha draft → GREEN RO → GREEN mutators → Zara → AMBER; one-flag direct-executor rollback + exact-`APP_VERSION` rollback documented; legacy deletion blocked by 30 green days + game-day + caller scan + `/health`
- **Next exact action (OWNER):** AUTH-DEPLOY decision; only after deploy evidence, separately authorize shadow flag arm and each subsequent canary promotion/soak. Legacy deletion remains a later separate owner decision.
- **Out of scope:** Any deploy/flag arm/promotion/deletion without owner authorization · plan-file edits · stock wheel/direct embedding/default tools/direct provider access · voice migration

---

## WS-GTM1 Hot Queue → 2nd paid (CURSOR LANE B)
- **ID:** WS-GTM1
- **Business outcome:** 2nd paying Marketing customer this week via Hot Queue outreach execution
- **Current state:** Technical READY · business blocker is still owner execution at `/app/inbox`
- **Next exact action:** Owner daily Hot Queue blitz (15 min/day) + manual UPI approval when payment arrives
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
- **WS-HYG** Duplicate/docs hygiene 2026-08-14 — playbook templates + root orphans + deploy footguns archived; evidence `docs/evidence/HYGIENE_MERGE_20260814.md`
- **WS-GOV** Boss + Second Brain governance (flag OFF)
- **WS-BUZZ** Local Buzz Desktop + relay (Cursor ACP Boss canonical `1b13cecc`, relay verified)
- **WS-DEP329** Rollback retention lineage
- **WS-REV** #306 live proofs (after #304 guest bind proven)
- **WS-AMAX** DUNNING safe-enabler (#307 stays OFF per owner decision)
- **WS-SEC1** Vobiz credential rotation
- Creative OS expansion · Swara/voice (FROZEN) · Stage B AMBER OpenClaw
