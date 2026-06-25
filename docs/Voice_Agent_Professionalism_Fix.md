# Voice Agent Professionalism — Root Cause Analysis & Fix Plan

> **Date:** 2026-06-24  
> **File:** `app/voice_agent/telecaller_brain.py` (lines 1578–1618)  
> **Status:** 1 critical bug found + 3 tuning recommendations

---

## 1. Root Cause: `_clean()` Truncation Bug 🔴 (CRITICAL)

**Location:** `telecaller_brain.py` lines 1608–1617

```python
parts = re.split(r"(?<=[।.?!])\s+", t)
if len(parts) > 2:
    t = " ".join(parts[:2]).strip()
# hard word cap (~20) — trim at a clause boundary, never mid-thought.
words = t.split()
if len(words) > 20:
    t = " ".join(words[:20]).rstrip(" ,;—-")
    if not re.search(r"[।.?!]$", t):
        t += "?"
```

**Kya hota hai:**

1. LLM ek natural 28-word response likhta hai:  
   *"Haan sir, main Swara hoon LeadGen AI se. Aapke business ke liye roz qualified leads dilati hoon, Instagram aur Google pe automatic posts bhi banati hoon. Kya aapko bhi yeh chahiye?"*

2. `_clean()` pehle 2 sentences le leta hai (step 1), fir unko 20 words me kaat deta hai (step 2):  
   *"Haan sir, main Swara hoon LeadGen AI se. Aapke business ke liye roz qualified leads dilati hoon, Instagram aur Google pe"* (20 words, **mid-thought cut**)

3. Step 3: `?` append karta hai kyunki ending me `.` ya `!` nahi hai:  
   *"Haan sir, main Swara hoon LeadGen AI se. Aapke business ke liye roz qualified leads dilati hoon, Instagram aur Google pe?"*

**Result:** Customer ko ek **incomplete sentence** sunta hai jo **question bhi nahi hai** par `?` ke saath khatam hota hai. Yeh "robotic", "confused", aur "unprofessional" feel deta hai — **yahi #1 problem hai.**

---

## 2. Secondary Issues 🟡

### 2.1 TTS Prosody Inconsistency (Phone vs Web)
- **Phone stream:** `PHONE_TTS_RATE="+0%"` (default = no speed change) → slow/monotonous feel
- **Vobiz stream:** `VOBIZ_TTS_RATE="+8%"` (default = snappier) → natural pace
- **Fix:** Phone stream bhi `+8%` set karo (ya dono ko `+5%` + `+2Hz` pitch)

### 2.2 Free LLM Primary → Lower Quality Hinglish
- **Current:** `free_ai.chat()` PRIMARY (Cerebras → Groq → OpenRouter) — free models, fast but less natural Hinglish
- **Gemini:** Fallback pe hai — better Hinglish, larger context, more nuanced tone
- **Fix:** `VOICE_GEMINI_PRIMARY=1` set karo (ya `.env` me `GEMINI_PRIMARY=1`) — Gemini becomes PRIMARY for voice

### 2.3 Mirror Acknowledgments Repetitive
- `_mirror_ack()` sirf 5 rotating phrases use karta hai: `"Samajh gayi ji —"`, `"Bilkul ji —"`, `"Theek hai ji —"`, `"Ji —"`, `"Achha ji —"`
- 3-4 turns ke baad customer pattern notice kar sakta hai
- **Fix:** 8-10 varied phrases add karo + context-aware (e.g., objection pe different ack, positive reply pe different ack)

### 2.4 `_clean` Word Cap Too Aggressive
- 20 words = ~4-5 seconds bolne ka time (phone pe acceptable but clipped)
- Industry best practice: 1-2 short sentences = ~15-30 words, NOT hard-cut at 20
- **Fix:** 25-30 word cap with sentence-boundary truncation (not word-count truncation)

---

## 3. Fix Plan (Priority Order)

### Fix 1: `_clean()` Rewrite — Sentence-Boundary Truncation + No Fake `?` 🚨
**File:** `app/voice_agent/telecaller_brain.py` (lines 1608–1618)
**Effort:** ~30 min
**Impact:** HIGH — fixes #1 unprofessional feel

```python
# OLD (buggy):
parts = re.split(r"(?<=[।.?!])\s+", t)
if len(parts) > 2:
    t = " ".join(parts[:2]).strip()
words = t.split()
if len(words) > 20:
    t = " ".join(words[:20]).rstrip(" ,;—-")
    if not re.search(r"[।.?!]$", t):
        t += "?"

# NEW (correct):
# 1. Split into sentences, keep up to 2 COMPLETE sentences
parts = re.split(r"(?<=[।.?!])\s+", t)
if len(parts) > 2:
    t = " ".join(parts[:2]).strip()
# 2. Soft word cap: if 2nd sentence makes it >28 words, drop it
words = t.split()
if len(words) > 28:
    # Keep only the 1st complete sentence
    t = parts[0].strip() if parts else t
# 3. NEVER append fake punctuation — if incomplete, just end gracefully
#    (the sentence-boundary split above keeps complete sentences only)
```

**Key changes:**
- 20 → 28 word cap (more natural breathing room)
- Truncate at **sentence boundary**, not word count
- **Never append `?`** artificially — if we can't complete, drop the partial sentence entirely
- If 2 sentences exceed 28 words, keep only sentence 1 (complete, natural)

### Fix 2: Mirror Ack Variations 🔧
**File:** `telecaller_brain.py` line 684–691 (`_mirror_ack`)
**Effort:** ~15 min
**Impact:** MEDIUM — reduces repetitive feel

Add 5 more varied acknowledgments:
```python
acks = (
    "Samajh gayi ji —",
    "Bilkul ji —",
    "Theek hai ji —",
    "Ji —",
    "Achha ji —",
    "Haan ji —",
    "Bilkul samajh gayi —",
    "Sahi baat hai ji —",
    "Aapki baat clear hai —",
    "Bilkul sahi —",
)
```

### Fix 3: TTS Rate Alignment 🔧
**File:** `.env` (VPS pe)
**Effort:** 2 min
**Impact:** LOW — natural pacing

```bash
PHONE_TTS_RATE=+8%
PHONE_TTS_PITCH=+2Hz
```
(Phone stream `+0%` → `+8%` to match vobiz_stream default)

### Fix 4: Gemini Primary for Voice 🔧
**File:** `.env` (VPS pe)
**Effort:** 2 min
**Impact:** MEDIUM — better Hinglish quality

```bash
VOICE_GEMINI_PRIMARY=1
# Ya agar global chahiye:
GEMINI_PRIMARY=1
```

---

## 4. Verification After Fix

1. **Web-call test:** `leadsgenai.in/app/test-call` → 4-5 turn conversation → listen for:
   - No incomplete sentences ending in `?`
   - Natural sentence completion
   - Varied ack phrases
   - Snappy, confident pace (TTS rate)

2. **Agent tester:** `python scripts/agent_tester.py` → check:
   - No BANNED phrases (already working)
   - No REPEAT (already working)
   - No TOO LONG (should decrease with 28-word cap)
   - No EMPTY (already working)

3. **Real conversation test:** Call a friend/family → ask:
   - "Kya agent professional lag rahi thi?"
   - "Kya koi incomplete sentence suna?"
   - "Kya wahi line baar-baar repeat ho rahi thi?"

---

## 5. Summary

| Issue | Severity | Fix | Effort |
|-------|----------|-----|--------|
| `_clean` truncates mid-sentence + fake `?` | **CRITICAL** | Sentence-boundary truncation, 28-word cap, no fake `?` | 30 min |
| Mirror acks repetitive (5 only) | MEDIUM | Expand to 10 varied phrases | 15 min |
| TTS rate `+0%` (phone) vs `+8%` (vobiz) | LOW | `PHONE_TTS_RATE=+8%` | 2 min |
| Free LLM primary → lower quality Hinglish | MEDIUM | `VOICE_GEMINI_PRIMARY=1` | 2 min |

**Total fix time:** ~50 min  
**#1 fix:** `_clean()` rewrite — yeh karne se professionalism ka sabse bada gap fix hoga.

---

*Analysis from: `telecaller_brain.py` lines 1578–1618, `phone_stream.py`, `vobiz_stream.py`, `agent_tester.py`*
