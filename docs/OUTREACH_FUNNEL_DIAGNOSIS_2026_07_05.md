# Outreach Funnel Diagnosis — 2026-07-05

**Trigger:** LLM council flagged "~2000 emails → 0 replies = broken distribution funnel" as the #1 issue. Before acting, I pulled the REAL numbers from the live VPS (`data/` bind-mount). **The council's premise was HALF WRONG — and the correction changes the entire recommended next move.**

## What's actually true (live data, 2026-07-05)

| Metric | Value | Source |
|---|---|---|
| Total prospects | **7,654** | `data/prospects.jsonl` |
| Prospects WITH an email address | 2,025 (26%) | 5,629 are phone-only scrapes |
| Emails sent (`emailed_at` set) | **1,995** | matches `email_warmup.json` total 1,994 |
| Got ≥1 follow-up | 1,541 | multi-touch sequencing works |
| Pending emailable | 28 | **emailable list is essentially exhausted** |
| **Reply drafts captured** | **1,737** | `data/reply_drafts.jsonl` (483KB, fresh today) |
| — "interested" | **338** | |
| — "question" | 19 | |
| — "objection" | 18 | |
| — "other" (bounces/OOO/auto) | 1,343 | classifier lumps non-replies here |
| — unsubscribe | 1 | (spam-complaint signal ≈ zero) |
| Reply drafts last 14 days | 1,308 | actively flowing |
| Paying customers | ~1 | |

## The correction

- **"0 replies" is FALSE.** The reply-agent (`REPLY_AGENT=1`, IMAP derived from `smtp.hostinger.com`) IS reading the inbox and drafting responses — 1,737 drafts, **~357 genuinely warm (interested/question/objection)**, 1,308 in the last 2 weeks.
- **The outreach MACHINE works.** Sends, warmup ramp, follow-ups, dedup (`emailed_at`), SPF/DKIM/DMARC monitoring, reply capture, AI-drafting — all functioning. This is NOT a broken-pipeline / deliverability-collapse problem (1 unsubscribe across ~2000 sends = mail is landing, people are engaging).
- **The real leak is the HUMAN-IN-THE-LOOP conversion step.** ~338 interested leads have AI-drafted replies sitting in the hot-queue, and only ~1 became a customer. Auto-send is OFF by design (ban-safe) — so drafts wait for a human to review→send→book. Nobody is working the warm inbound.

## Corrected recommendation (supersedes "fix distribution")

**The bottleneck is NOT top-of-funnel acquisition — it's converting the ~357 warm replies already sitting in the inbox.** The leads are captured, classified, and pre-drafted. This is the single highest-ROI move and needs zero new engineering:

1. **Work the Hot Queue NOW** — `/app/office` → Hot Queue (or `/app/inbox`) surfaces exactly these interested/question replies with AI drafts. Founder: review draft → personalize 1 line → send → book a call/demo. 338 interested leads → even 3% close = ~10 customers (the stated goal).
2. **Fix the "other" bucket (1,343)** — many are bounces/OOO misclassified. Quick win: improve reply-agent classification so genuine replies don't hide in "other" (a real leak — some of those 1,343 may be interested-but-miscategorised).
3. **Refill the emailable list** — only 28 pending; 5,629 prospects have NO email. Email-finding + verified (not just MX-guessed) addresses to keep the top of funnel fed AFTER the warm backlog is worked. Secondary to #1.

## Honest caveats

- "interested: 338" is the reply-agent classifier's label — some may be soft/polite-no; the real number of true buyers is lower, but even a heavy discount leaves dozens of workable warm leads.
- "other: 1,343" likely includes many bounces/auto-replies — so the true human-reply rate is lower than 87%, but the ~357 warm bucket is a specific, actionable signal.
- Emails were sent to pattern-guessed (MX-only) addresses — list quality can improve, but it clearly wasn't fatal (people replied).

## Bottom line

The council was right that **distribution/conversion — not more voice features — is the priority**, but wrong on the mechanism. It's not "the funnel is broken and gets 0 replies." It's **"the funnel is FULL of warm, AI-drafted replies that aren't being worked."** First action = open the Hot Queue and close the ~357 warm leads, not send more cold email.
