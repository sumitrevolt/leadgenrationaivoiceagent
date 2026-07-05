---
name: retro
description: Weekly engineering retro — git se commits/features/bugs/streak nikaalo, prod-downs + learnings summarize karo, next-week top-3 priorities set karo. Use jab user bole "weekly retro karo", "is week kya kiya", "progress review chahiye", ya hafte ke end pe shipping momentum dekhna ho.
---

# Skill: retro
**Adapted from gstack by Garry Tan (YC). MIT License.**

## When to invoke
- "Weekly retro karo"
- Hafte ke end mein
- "Is week kya kiya?"
- "Progress review chahiye"

---

## Step 1: Raw Data Gather

```bash
# Is week ke commits
git log --oneline --since="7 days ago" --format="%h %s (%ad)" --date=short

# Files most changed
git diff --stat HEAD~20..HEAD | sort -t'|' -k2 -rn | head -20

# Total lines changed
git log --since="7 days ago" --numstat --format="" | awk '{add+=$1; del+=$2} END {print "Added:"add, "Deleted:"del}'

# Features shipped
git log --oneline --since="7 days ago" | grep -E "^[a-f0-9]+ (feat|fix|add|ship|live|deploy)" | wc -l
```

---

## Step 2: Metrics Compute

Calculate karo:
- **Commits this week:** total count
- **Features shipped:** commits with feat/add/live/deploy prefix
- **Bugs fixed:** commits with fix/hotfix/prod-down
- **Files changed:** unique file count
- **Prod-downs:** grep CLAUDE.md for PROD-DOWN this week

---

## Step 3: Wins + Learnings

### Wins (kya kiya)
List karo top 3-5 achievements (features shipped, bugs fixed, infra improvements).

### Prod Incidents
Agar koi prod-down tha: root cause + fix + prevention rule.

### Gotchas Learned
Koi nayi learning jo CLAUDE.md mein add honi chahiye.

---

## Step 4: Pipeline Health Snapshot

```bash
python scripts/prod_check.py 2>&1 | tail -3
```

Current state:
- Routes count
- Test pass/fail
- Live flags (ON vs OFF)
- Key pending user actions

---

## Step 5: Next Week Priority

Top 3 priorities for next week (based on TASKS.md + blockers):
1. [Most important — usually a blocker]
2. [Revenue/growth impact]
3. [Tech debt / reliability]

---

## Step 6: Shipping Streak

```bash
git log --format="%ad" --date=short | sort -u | tail -14
```

Kitne consecutive days commit kiya? Streak track karo — momentum matter karta hai.

---

## Step 7: RL dev-reward review (Loop B, optional)

Agar `data/claude_feedback.jsonl` exist kare to last week ki rows Read karo. Reward = `app.agents.rl.reward.dev_reward` (single source of truth — yahan recompute mat karo). Average dev-reward trend dekho:
- **Up / high** → jo dev-patterns kaam kar rahe (verify+tests+deploy green) unhe reinforce (memory/skill).
- **Down / negative** (user_correction, verify fail dohraye) → recurring anti-pattern ko ek `guard.py`/`skill_reminder.py` guardrail ya CLAUDE.md gotcha-line me convert karo.
Ye Claude (dev-time agent) ke self-improvement ka closed loop hai — naya dashboard NAHI, existing machinery hi.

---

## Output Format

```
## 🔁 Weekly Retro — [Date]

### 📦 Shipped
- [Feature 1] (commit abc123)
- [Feature 2] (commit def456)

### 🐛 Fixed
- [Bug 1] — root cause was X

### 📊 Numbers
- Commits: N | Features: N | Bugs: N
- Routes: N | Tests: N passing
- Streak: N days

### 💡 Top Learnings
1. [Lesson]

### 🎯 Next Week
1. [Priority 1]
2. [Priority 2]
3. [Priority 3]

### 🚨 Blockers (user action needed)
- [DLT, UPI, Vobiz, etc.]
```
