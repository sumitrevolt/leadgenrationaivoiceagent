# ACTIVE_WORK - max 3 workstreams

---

## WS-DSH DeepSeek Harness full migration (CURSOR LANE B)
- **ID:** WS-DSH
- **Business outcome:** Replace only the governed planning/turn/tool loop through a reversible, evidence-gated DSH path without introducing a second control plane or touching voice
- **Current state:** **FAIL-CLOSED/INERT, LOCAL-ONLY** · hardened source build + smoke + SBOM green · clean-build executable hashes still differ despite equal closure proofs and SEA suffix normalization · `DSH_RUNTIME_ENABLED=0`, `DSH_SHADOW_ENABLED=0`
- **Prep completed:** Hardened Cordis closure, pkg-visible config path, Linux fake MCP/model lifecycle smoke, CycloneDX SBOM, and CI blocker artifact
- **Next exact action (OWNER/BUILD):** Do not deploy or arm shadow. Either achieve bit-identical executable output or explicitly accept a non-bit-identical binary policy backed by content-addressed closure proof; all later rollout gates remain separate.
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
