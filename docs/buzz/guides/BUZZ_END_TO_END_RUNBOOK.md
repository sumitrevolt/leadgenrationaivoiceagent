---
title: "Buzz End-to-End Runbook — multi-harness + OmniRoute combos"
tags: [buzz, omniroute, codex, goose, opencode, freebuff, cost, runbook]
status: active
created: 2026-08-09
---

# Buzz End-to-End Runbook

Existing setup (2026-08-03) already gave us the workspace: relay, 11 channels,
four Claude-harness agents, autonomy policy, claim-before-edit locks. This
runbook covers what was missing — **more than one harness, and a lane that does
not burn subscription quota.**

Read `BUZZ_OPERATING_MODEL.md` first for the three-plane split. Nothing here
changes it: Buzz is still an interface, Boss is still the only route into the 31
runtime STAFF, and no Buzz agent is a 32nd STAFF persona.

## 0. Why this exists — the measured constraint

`python scripts/buzz_agent_cost.py --days 7` on 2026-08-09:

| | 7-day total |
|---|---|
| Claude Code | 591M tokens · 2,020 calls |
| Codex | 266M tokens · 1,810 calls |
| Codex subscription | **peaked at 100% used** |
| Counterfactual at API list price | ~$483 (≈₹42.5k) |
| Actual marginal cost | **₹0** (subscription stack) |

**Scope:** these are **all local sessions on this machine**, not just this repo —
correct for a quota argument, since quota is per-subscription, not per-project.
For project-only Claude figures pass `--project leadgen` (that flag filters
Claude sessions only; Codex totals stay machine-wide).

The video's "$200/day" is not our problem — we pay nothing per token. **Quota
is the constraint.** Codex hit 100%. When it does, the Codex-harness agent stops
answering and the cross-check lane goes dark.

That is the whole reason OmniRoute is in this runbook: a free-provider lane that
absorbs the high-volume, low-stakes work so the subscription quota is there when
the hard work needs it.

Run the cost report before you add agents, not after:

```bash
python scripts/buzz_agent_cost.py --days 7
python scripts/buzz_agent_cost.py --post     # posts the table to #ops
```

## 1. Two classes of participant — do not mix them

This is the distinction the video glosses over and it decides what you can
actually build.

**ACP agents** live *in* Buzz. Own Nostr keypair, channel membership, wake on an
@mention. They need a **headless ACP binary**.

| Agent | Harness | Binary | Status |
|-------|---------|--------|--------|
| Boss | claude-agent-acp | `%APPDATA%\npm\claude-agent-acp` | LIVE |
| Honey | claude-agent-acp | same | LIVE |
| Fizz | claude-agent-acp | same | LIVE |
| Bumble | claude-agent-acp | same | LIVE |
| **Comb** | **codex-acp** | `%APPDATA%\Buzz\node-tools\codex-acp` (Buzz ships it) | **CODE-READY** |
| _(optional)_ Goose | goose | `~/.local/bin/goose` v1.45.0 | available, not created |

**Keyboard-side tools** are driven by a human at a terminal or IDE. They never
join a channel. They take a **file lock** and post to `#build` with a prefix.

| Tool | Prefix | Why it can't be an ACP agent |
|------|--------|------------------------------|
| Cursor | `[CURSOR]` | IDE, no headless ACP mode |
| Claude Code CLI | `[CLAUDE]` | is a CLI, not the ACP harness |
| Codex CLI | `[CODEX]` | ditto (the *agent* uses codex-acp) |
| Goose | `[GOOSE]` | usable either way; currently keyboard-side |
| OpenCode | `[OPENCODE]` | config + db present, **no binary on PATH** |
| Freebuff | `[FREEBUFF]` | Electron desktop app, no headless binary |
| Monkey Code | `[MONKEY]` | experiments only |

**OpenCode and Freebuff cannot be Buzz agents.** Their whole integration is the
lock prefix and the `#build` handoff format — that is not a shortcut, it is the
complete and correct wiring for a GUI/interactive tool.

All seven are registered in `scripts/buzzlock.py`. A tool missing from that list
edits the shared tree with no lock at all.

**Source of truth for the tool list is `TOOLS` in `scripts/buzzlock.py`.** The
same table also appears in `CODING_AGENT_PROTOCOL.md`, `docs/coordination/README.md`
and the `#build` canvas — those are *published mirrors*, not independent copies.
Adding an eighth harness means editing `TOOLS`, then refreshing the mirrors with
`python scripts/buzz_admin_setup.py --apply` and a pass over the two docs. The
pinned-line tests in `tests/test_buzz_plane.py` fail if a mirror silently drops
something.

## 2. Adding the Codex agent (Comb)

Different harness = genuinely independent second opinion. Same harness twice is
theatre.

```bash
python scripts/buzz_setup_apply.py            # dry-run, prints the plan
python scripts/buzz_setup_apply.py --apply    # opens the draft in Buzz Desktop
```

`buzz agents draft-create` only carries channel, display name and system prompt.
**Harness, model and permissions are chosen in the Desktop form** — the script
prints exactly what to set. The agent is CODE-READY until you click Save; it is
LIVE only after.

### Why this cannot be fully scripted (verified 2026-08-09, stop re-deriving it)

`agents draft-create` fails with `auth error: agent draft requests require
BUZZ_AUTH_TAG` — the NIP-OA owner attestation. Three places were checked and the
tag is in none of them:

- **Windows Credential Manager** (`secrets.buzz-desktop`) holds the owner
  `identity` plus one `agent:<pubkey>` key per existing agent — **no auth tag**.
  `secrets.buzz-auth-tag`, `buzz-desktop` and `secrets.buzz` do not exist.
  (`scripts/buzz_authtag_probe.py` prints this shape; it never prints a value.)
- **The relay** serves only a NIP-11 JSON info document — there is no web UI to
  drive with a browser.
- **Buzz Desktop opens no listening port**, so there is no local API to ask for
  a tag.

Buzz Desktop mints the attestation in-process. Agent creation is therefore a
Desktop UI action by the owner — not a gap in this runbook, a property of the
product. Everything else in the workspace *is* scriptable (canvases, notes,
messages, mem, workflows, projects, patches), and is scripted.

Verify: @mention Comb in `#dev` **with a resolved mention chip**. Plain text that
looks like a mention does not wake a Buzz agent, and a thread reply without a
fresh mention does not retrigger one. A workspace that looks dead is almost
always this.

## 3. The cross-check pattern — owner-routed, not autonomous

The video shows agents commanding agents. We deliberately do not.
`AGENT_ROLES.md` sets respond-policy to **owner-only** precisely to stop @-loops,
and that decision stands. Cross-checking here means the owner routes the second
opinion, and the two harnesses never call each other.

```
owner: @Fizz implement X          (Claude Code harness)
Fizz:  patch + evidence in #dev
owner: @Comb review Fizz's patch  (Codex harness)
Comb:  findings with file:line + confidence + severity
owner: decides
```

Rules that make it worth doing:
- **Coverage, not filtering.** Comb reports everything with confidence and
  severity. Telling a reviewer "only high-severity issues" makes it withhold
  real bugs — recall drops while it looks more precise.
- **Different harness or don't bother.** Two Claude agents reviewing each other
  correlate their mistakes.
- **Evidence or it didn't happen.** Exit codes, pytest output, `/health.version`.
- **Locks always.** `--tool CODEX` claims before reading widely, releases after.

## 4. The OmniRoute combo lane

OmniRoute is a **local OpenAI/Anthropic-compatible gateway** on
`http://127.0.0.1:20128/v1` that fans out to free providers via named *combos*.
It is not Buzz's backend and not a training system — it is a routing layer.

Existing combo `leadgen-project-best` (priority order, all smoke-tested
2026-08-06): Groq Llama 3.3 70B → Mistral Code → Cerebras GPT-OSS 120B → Kiro
Qwen3 Coder Next → OpenCode DeepSeek V4 Flash Free.

### Bring-up (it is not running by default)

Lives in WSL Ubuntu-24.04 under tmux `leadgen-omni`, pinned to Node 22.

```bash
powershell -ExecutionPolicy Bypass -File scripts\start-leadgen-dev.ps1
powershell -ExecutionPolicy Bypass -File scripts\omniroute-check.ps1
```

**Readiness is `/v1/models` = 200, not a listening port.** A 401 on `/api/health`
means alive-and-auth-protected, not broken.

### Three lanes, honestly labelled

| Lane | What | Status |
|------|------|--------|
| **A — subscription** | Buzz agents on claude-agent-acp / codex-acp | PROVEN, live today |
| **B — keyboard via OmniRoute** | `scripts\start-claude-omniroute.ps1` | PROVEN (DryRun passed 2026-08-03; free-route smoke returned `AGENT_OS_SMOKE_OK`) |
| **C — Buzz agents via OmniRoute** | `scripts\start-buzz-omniroute.ps1` | **UNVERIFIED** |

Lane C detail: `claude-agent-acp`'s bundle **references** `ANTHROPIC_BASE_URL`,
`ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_MODEL` — that is a grep hit in `dist/`,
i.e. presence of the names, not proof of behaviour. And even if the harness does
honour them, it is separately unproven that Buzz Desktop forwards a process env
block down to the harness it spawns. Two unknowns, not one. The wrapper therefore:

- refuses to launch unless `/v1/models` answers 200 (exit 2),
- sets env **process-scoped only** — never `setx`, never the real Buzz you click,
- is **preview by default**; `-Launch` starts it,
- and tells you to verify by @mentioning an agent and checking the OmniRoute call
  log. **Traffic in the log is the proof. A launched app is not.**

If no traffic appears, Lane C does not work on this Buzz build — fall back to
Lane B, which does, and say so rather than assuming.

### Verified 2026-08-09 — the combo actually runs

Bring-up succeeded (Redis PONG, tmux `leadgen-omni`, `:20128` UP) and:

- `/v1/models` = **200**, and `leadgen-project-best` **is addressable as a model
  id** (alongside `leadgen-free-first` and `leadgen-swara-live`). This matters:
  Lane C sets `ANTHROPIC_MODEL=leadgen-project-best`, so if the combo were not a
  routable model id the lane would 404 on every request.
- A synthetic completion through the combo returned `COMBO_SMOKE_OK`, **served by
  `llama-3.3-70b-versatile`** — Groq, the combo's priority-1 target, exactly as
  configured. The fallback chain is real, not just saved.

**Auth, resolved with evidence.** The 2026-08-06 worry was that routing worked
only via anonymous loopback fallback. Re-tested both ways today: the
**authenticated** request returned 200 with a real completion, so the key *is*
accepted. The **anonymous** request also returned 200 — loopback does not enforce
auth. So: the key works, but it is not load-bearing. Never expose `:20128` beyond
loopback, because there is no auth wall behind it.

Note the gateway answers **SSE** (`data: {...}` lines), not a single JSON
document. Code that calls `ConvertFrom-Json` / `.json()` on the whole body fails
with "Invalid JSON primitive" — reassemble the deltas instead.

Repo-side gates `OMNIROUTE_ENABLED` and `OMNIROUTE_AGENTS` are both **unset** —
the double gate in `app/platform/omniroute_client.py` is closed, which is the
correct default. Nothing in this runbook opens it.

## 5. Multi-machine

The video's multi-machine story is two laptops. Ours is a laptop and a
production VPS, and that changes the answer.

**Never put a write-capable agent on the VPS.** It holds the prod SSH key, the
real `.env`, and the live customer database. Handing an agent that host is
handing it all three — Buzz's identity isolation does not undo an over-permissioned
credential underneath it.

The pattern already in use is correct and stays: `scripts/buzz_staff_pulse.py`
runs on Windows, SSHes read-only, and posts a mirror into `#staff-pulse`.
Multi-machine = a second read-only reporter, not an agent living on prod.

Note the laptop constraint the video is honest about: a locally-running agent
needs the machine awake. Phone control does not turn a sleeping laptop into a
server.

## 6. Mobile and audio

Both are Desktop/app actions the owner performs — there is nothing to wire.

- **Mobile pairing:** pair from Buzz Desktop, don't create a second identity for
  the phone. A separate key is a separate member with separate channel
  membership, and mentions routed to it will look like they vanished.
- **Audio huddles:** humans and agents in one call. Treat the huddle as input,
  not as a decision record — anything agreed there needs a `#admin` message or a
  canvas edit afterwards, or it is not in the audit log.

## 7. Hermes — superseded, not adopted

The video's third integration path is Nous Research's Hermes Agent as a
non-subscription harness. We already have that role filled by OmniRoute: local,
free-provider, combo-based, and wired into this repo since July. Adding Hermes
would add a vendor for a capability we have.

There is also a hard blocker: **Hermes 🛰️ is already one of the 31 runtime STAFF**
(Infrastructure Handler, `app/platform/team.py`). A Buzz agent by that name
collides with an existing persona, and inventing a 32nd STAFF persona is a
RED-tier refusal in `AUTONOMY_POLICY.md`. Not adopted, by decision.

## 8. Daily loop

```bash
python scripts/buzzlock.py status                 # who holds what
python scripts/buzz_agent_cost.py --days 1        # quota burn + counterfactual
python scripts/buzz_staff_pulse.py --dry-run      # 31 STAFF mirror
```

Weekly: `python scripts/buzz_agent_cost.py --days 7 --post` into `#ops`. Watch the
Codex peak — that number reaching 100% is what takes the reviewer offline.

## 8a. The grid DOES route work — and Boss's failure is an identity problem

Corrected 2026-08-09 11:0x. An earlier canary was declared failed at a 240-second
bound; **Honey actually replied at 7m42s** (`#dev` `9b0a14c4…`, `e`-tagged to
request `0a6a3c42…`) with a correct, file:line-cited, scope-bounded artifact — and
it caught a real defect in `buzzlock.py` (see §9, exit-code ambiguity).

**Agent turnaround is ~7–8 minutes. Bound any canary at ≥600 s.** A 240 s bound
manufactures false NO-GOs; that mistake is what §8b below originally recorded.

### Why Boss specifically is silent — and how to fix it without the Desktop UI

`buzz-acp.exe` is the harness binary and it takes the identity directly:

```
buzz-acp.exe --relay-url wss://leadsgenai.communities.buzz.xyz \
             --private-key <from credential store, env only> \
             --agent-owner <owner pubkey> \
             --agent-command claude-agent-acp \
             --subscribe mentions
```

So a harness does **not** require the Desktop UI — Desktop simply never spawned
one for Boss. The credential store holds keys for Honey, Fizz, Bumble **and**
Boss `1b13cecc`; three of those four have a running harness. Boss is the odd one
out, and the Boss that *is* a channel member (`20b69265`) has **no key here at
all**. That is the whole failure: an identity Desktop can run is not in the
channels, and the identity in the channels cannot be run.

`scripts/buzz_start_harness.py` implements the launch. **It is unverified** — the
sandbox guardrail in the authoring session refused to execute or even lint it,
because reading an agent private key and spawning a process with it is a gated
capability. Review it, then run `--dry-run` (which returns before touching the
key) before the real start.

## 8b. Superseded — the original (wrong) reading of the canary

> **Read §8a first.** The "no reply" below was a 240-second bound, not a dead
> grid — Honey answered at 7m42s. Findings 1 and 2 remain accurate; finding 3 is
> the one that was misread.

A real canary (`GRID-CANARY-20260809-104317`, `#dev` event `0a6a3c42...`) sent a
**resolved** mention — the relay echoed `mention_pubkeys: [b9ffabcf...]`, so this
was a genuine chip, not lookalike text — asking Honey for a read-only repo
fact-check. Three findings, all reproducible from the CLI:

1. **Boss has no running harness.** `users presence` returns only Honey, Fizz and
   Bumble. Three `buzz-acp.exe` processes run; none is Boss. Every documented
   grid path starts at Boss, so the chain cannot begin.
2. **Boss is triplicated.** `users get --name Boss` returns `20b69265` (the
   channel member, last posted 08-05), `1b13cecc` (the key held in *this*
   machine's credential store, last posted 08-03) and `bcf2f580` (never posted).
   The identity a mention resolves to is not the identity this laptop can run.
3. **Presence is a heartbeat, not readiness.** Honey/Fizz/Bumble were `online`
   with `last_seen` 6 minutes old, yet no agent has posted in any channel since
   08-05. Never accept a green badge as grid proof — send a canary and require a
   correlated reply.

Diagnosing *why* a live harness ignores a resolved mention needs the Desktop UI
(agent card, respond policy, channel subscriptions). That is owner-side.

## 9. Gotchas that have already cost time

- Buzz agents wake **only** on a resolved @mention chip. Not on lookalike text,
  not on a thread reply without a fresh mention.
- `LOCKS.json` is gitignored and per-checkout. `buzzlock` self-initialises now;
  before 2026-08-09 it raised `FileNotFoundError` on every fresh worktree, so the
  lock protocol was silently skipped.
- `buzzlock claim` exit **2** means another tool holds the file. It is a stop, not
  a warning.
- OmniRoute lives in **WSL**, not Windows. `omniroute` is not on the Windows PATH
  and the npm global entry is a stub.
- **A literal `@word` anywhere in message text is parsed as a mention and the
  relay REJECTS the whole send** if it doesn't match a channel member
  (`mention '@foo' does not match a current channel member`). Writing *about*
  mentions costs you the message. Reword, or pass `--mention <pubkey>` which
  makes unresolved `@Name` text presentation-only.
- Send a **resolved** mention with `messages send --mention <pubkey>`; the
  response echoes `mention_pubkeys` — that echo is your proof the chip resolved.
- `buzz messages edit` returns **rc=0 but `messages get` still returns the
  original event** — an edit is a separate Nostr event and only a client that
  merges them shows the new text. Do not trust rc=0 as proof the workspace now
  reads correctly. For anything load-bearing, post a visible correction instead
  of relying on an in-place edit.
- `canvas set` **replaces** the whole document. Read it first
  (`buzz_admin_setup.py --dump`) — both live canvases were hand-written and a
  blind write would have deleted them.
- The gateway answers **SSE**; whole-body JSON parsing fails with "Invalid JSON
  primitive". Reassemble the `data:` deltas.
- Inline PowerShell through bash mangles `$variables` and nested quotes. Write a
  script file and run it — three sessions have lost time to this.
- Windows consoles are cp1252 and die on `₹`/`≈`. Reconfigure stdout to UTF-8
  rather than dropping the characters.
- Never `git add -A`. Several tools edit this tree at once.
