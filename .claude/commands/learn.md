---
description: Session ka reusable pattern/gotcha extract karke sahi jagah (SESSION_LOG / CLAUDE.md / naya skill / memory) durably save karo — dedup + quality-bar ke saath.
---
# /learn — reusable knowledge capture (engineer-grade)

Koi non-trivial problem solve karne / debug / wiring ke BAAD chalao. Goal: **next time re-derive na karna pade** — knowledge ko sahi durable jagah, sahi shape me daalo. Token bachao, future-you (ya agent) ko cold-start se bachao.

## Step 0 — Capture-worth hai? (quality gate)
Sab kuch save mat karo — noise = future cost. Save SIRF jab **>=1 TRUE**:
- **Non-obvious tha** — code/git/CLAUDE.md padh ke pata nahi chalta; tune dhoondhne me time/tokens lage.
- **Repeatable** — phir aayega (recurring gotcha, library quirk, project convention).
- **Costly-to-rediscover** — prod-down, silent failure, ya 3+ attempt lage.

**SKIP karo** (yeh save MAT karo):
- Jo repo khud record karta — code structure, file locations, route names, past commits/git history.
- One-off facts jo sirf is conversation me matter karte.
- "X file me Y function hai" — woh grep kar lega; pattern/gotcha capture karo, location-dump nahi.

> Agar user ne aisi cheez "yaad rakho" boli jo repo already record karta → poochho **kya non-obvious tha** us baare me, aur WAHI save karo.

## Step 1 — Extract: structured `Symptom → Root cause → Fix`
Ek-do line, reusable shape me. 3 categories:
- **Gotcha → fix**: error/symptom → ASLI root cause → fix + *guard* (taaki dobara na ho). e.g. "Pollinations 402 → `POLLINATIONS_API_KEY` unset → graceful 402 + UI fallback", "first-route-wins → naya route add se pehle `grep '@router'`".
- **Workaround**: library/API/version quirk, env-specific trick (base64-over-ssh, Windows `os.kill`→ctypes, stale sandbox mount → Windows=truth).
- **Pattern/convention**: codebase discipline (flag-gated · inert-without-creds · never-raise-in-public-route · ML asset = bake+off-loop+deadline+disable-switch).

## Step 2 — Dedup check (PEHLE search, fir likho)
Duplicate knowledge = stale-risk. Likhne se pehle:
1. `Grep` SESSION_LOG.md + CLAUDE.md + relevant `.claude/skills/` for the keyword.
2. **Match mila → UPDATE** us existing entry/skill ko (naya banane se behtar). **Nahi mila → naya** banao.

## Step 3 — Kahan save (decision tree)
| Knowledge | Jagah |
|---|---|
| Chhota dated gotcha / incident / build note | `docs/SESSION_LOG.md` (append, date + SHA) |
| **Hot, har-turn-relevant** env/infra gotcha | CLAUDE.md me 1-line ("Critical Env Gotchas") — *sirf agar truly recurring; LEAN rakho* |
| **Reusable multi-step workflow** | Naya/updated `.claude/skills/<name>/SKILL.md` |
| User preference / feedback / project-fact (cross-session) | Auto-memory `memory/` + `MEMORY.md` pointer |

Doubt ho to **SESSION_LOG default** — CLAUDE.md aur skills costly hain (har turn / discovery overhead).

## Step 4 — Skill banao to (format)
- Path: `.claude/skills/<kebab-name>/SKILL.md` (repo file — managed-skills cache READ-ONLY, usme mat likho).
- Frontmatter: `name:` (kebab) + `description:` with **trigger phrases** (jab user X bole → yeh skill) — `leadgen-ops` / `marketing-feature` ka format copy karo.
- Body: lean, action-first, project-specific gotchas inline. Non-trivial = `writing-skills` skill invoke karke discipline follow karo.

## Step 5 — Verify + report
- File **Windows file-tools se** likho (sandbox stale; CLAUDE.md/SESSION_LOG bash-append KABHI nahi — mid-file corrupt hota).
- Likhne ke baad target file Read karke confirm karo (entry actually landed).
- **Output**:
```
LEARN: saved
where:   <SESSION_LOG | CLAUDE.md | skill:<name> | memory:<slug>>
action:  new | updated <existing>
summary: <1-line — symptom → fix/pattern>
```

`$ARGUMENTS`: optional topic/hint (e.g. `learn telephony` = is session ka telephony-related sabak capture karo). Khaali = poora session scan.

## Step 6 — RL dev-reward consumption (Loop B, optional)
Agar `data/claude_feedback.jsonl` exist kare to last ~30 rows Read karo. Har row ka reward = `app.agents.rl.reward.dev_reward` (verify_pass + tests_pass + deploy_health, minus user_correction/review_findings) — **single source of truth, yahan dobara mat compute karo**.
- **High-reward pattern** (verify+tests pass, deploy ok) → usko `memory/` feedback-note ya skill snippet me reinforce karo (jo upar Step 3 me already hota hai).
- **Low-reward** (user_correction true / verify fail) → ek guardrail propose karo: `guard.py` ya `skill_reminder.py` me entry, taaki wo anti-pattern dobara na ho.
- User ne is session me "galat tha" type correction diya ho to wo signal yahin capture hota — agar chaho to last `claude_feedback.jsonl` row me `user_correction: true` set karke wo negative reward record karo.
Ye existing machinery (memory + skills + hooks) use karta — koi naya dashboard NAHI banana.
