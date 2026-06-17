---
name: doc-gen
description: Technical docs likho (Diataxis — reference / how-to / explanation / runbook) codebase padh ke. Use jab user bole "docs generate karo", naye module/feature/endpoint ke liye README ya API-doc chahiye, ops runbook (enable/health/rollback) banana ho, ya `docs/` outdated ho.
---

# Skill: doc-gen
**Adapted from gstack (document-generate) by Garry Tan (YC). MIT License.**

## When to invoke
- "Docs generate karo"
- Naya module/feature ke liye README/doc chahiye
- `docs/` outdated hai
- API documentation missing

---

## Step 0: Scope Define karo

User se poocho: **"Kaunsa module/feature ke liye doc chahiye?"**

Options:
- **API docs** — Endpoints ke liye (request/response format, auth, examples)
- **Module doc** — Ek Python module explain karo
- **Feature runbook** — Ops runbook (kaise deploy, kaise rollback, kaise debug)
- **Architecture doc** — System design explain karo

---

## Step 1: Codebase Read (Research Phase)

```bash
# Module samjho
cat app/[module]/feature.py

# Routes dhundo
grep -n "@router\." app/api/[file].py

# Tests se usage examples nikalo
cat tests/test_[feature].py | head -50

# Related skill agar hai
ls .claude/skills/ | grep -i "KEYWORD"
```

---

## Step 2: Doc Types (Diataxis Framework)

Gstack wala Diataxis use karta hai — 4 types:

| Type | Question it answers | Example |
|------|---------------------|---------|
| **Reference** | What is X? | API endpoints list |
| **How-to** | How do I do X? | "Email warmup enable kaise karein" |
| **Explanation** | Why does X work this way? | "Celery vs in-process scheduler kyun" |
| **Tutorial** | Learn by doing | "Apna pehla client onboard karo" |

---

## Step 3: Write Reference Doc First

```markdown
# [Module Name] — Reference

## Overview
[2-3 sentences: kya karta hai, kaun use karta hai]

## Configuration
| Env Var | Default | Description |
|---------|---------|-------------|
| `FLAG_NAME=1` | OFF | Enable karo tab |

## API Endpoints
### `POST /api/growth/feature`
**Auth:** Admin token required
**Rate limit:** 30/60s

Request:
```json
{"param1": "value", "param2": 123}
```

Response:
```json
{"ok": true, "result": {...}}
```

## Data Store
- File: `data/feature.jsonl`
- Fields: `id`, `created_at`, `status`

## Dependencies
- Requires: `EXTERNAL_API_KEY` set
- Uses: `app/platform/xxx.py`
```

---

## Step 4: How-To Guide

```markdown
# How to: [Task]

## Prerequisites
- [What needs to be set up first]

## Steps
1. [Action] → [Expected result]
2. [Action] → [Expected result]

## Verify karo
```bash
[verification command]
```

## Common errors
- **Error X**: Fix = Y
```

---

## Step 5: Ops Runbook (agar applicable)

```markdown
# Runbook: [Feature] Ops

## Enable karo
```bash
# VPS pe (env-change = recreate, sirf restart se naya env nahi uthta)
ssh root@72.61.245.204
cd /opt/leadgen
echo "FLAG=1" >> .env
docker compose -f docker-compose.vps.yml up -d --no-deps app
```

## Health check
```bash
curl https://leadsgenai.in/health
```

## Rollback
```bash
sed -i '/FLAG=1/d' .env
docker compose -f docker-compose.vps.yml up -d --no-deps app
```

## Logs dekho
```bash
docker logs leadgen_app --tail=100 | grep -i "FEATURE"
```
```

---

## Step 6: Save + Commit

```bash
# Save to right location
docs/API.md          # API reference
docs/[FEATURE].md    # Feature-specific
.claude/skills/[name]/SKILL.md  # If it's a workflow skill

git add docs/
git commit -m "docs: add [feature] documentation"
```
