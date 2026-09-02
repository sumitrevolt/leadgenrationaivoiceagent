"""
Obsidian Vault Historical Backfill
====================================
Reads existing data from memory_vault, lead_usage.jsonl, and docs/ADRs,
and writes them to the Obsidian staging vault as markdown files.

Run once after setting up the vault:
  OBSIDIAN_SYNC=1 python scripts/backfill_obsidian.py

Does NOT push to Git — run scripts/setup_obsidian_vault.sh first, then
trigger a manual push or wait for the nightly job.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("OBSIDIAN_SYNC", "1")

from app.platform.obsidian_sync import append_note, write_note  # noqa: E402

DATA = ROOT / "data"
DOCS = ROOT / "docs"
VAULT = DATA / "obsidian_staging"

print("[backfill] Starting Obsidian historical backfill...")
counts = {"leads": 0, "memory": 0, "adrs": 0, "coordination": 0}


# ── 1. Lead usage ledger → Leads/  ─────────────────────────────────────────
lead_file = DATA / "lead_usage.jsonl"
if lead_file.exists():
    print("[backfill] lead_usage.jsonl → Leads/...")
    by_ref: dict[str, list[dict]] = {}
    with lead_file.open(encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                slug = (rec.get("ref") or rec.get("client_id") or "unknown")[:20]
                slug = slug.replace("+", "").replace(" ", "")
                by_ref.setdefault(slug, []).append(rec)
            except Exception:
                pass
    for slug, recs in by_ref.items():
        lines = [f"# Lead: {slug}\n"]
        for r in recs:
            lines.append(
                f"- **{r.get('ts', '')[:10]}** — {r.get('kind', '?')} leads={r.get('leads', 0)} plan={r.get('plan', '?')}"
            )
        write_note("Leads", slug, "\n".join(lines), tags=["lead", "backfill"])
        counts["leads"] += 1
    print(f"[backfill]   → {counts['leads']} lead files written")


# ── 2. Memory vault prospect/client files → Leads/ + Clients/  ─────────────
memory_dir = DATA / "memory"
prospects_dir = memory_dir / "prospects"
clients_dir = memory_dir / "clients"

if prospects_dir.exists():
    print("[backfill] memory/prospects/ → Leads/...")
    for md_file in prospects_dir.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            slug = md_file.stem.replace("+", "").replace(" ", "")
            write_note(
                "Leads",
                f"mem-{slug}",
                f"# Memory: {slug}\n\n{content}",
                tags=["memory", "prospect"],
            )
            counts["memory"] += 1
        except Exception:
            pass
    print(f"[backfill]   → {counts['memory']} prospect memory files mirrored")

if clients_dir.exists():
    for md_file in clients_dir.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            slug = md_file.stem
            write_note("Clients", slug, f"# Client: {slug}\n\n{content}", tags=["memory", "client"])
            counts["memory"] += 1
        except Exception:
            pass


# ── 3. ADRs + key docs → Decisions/  ───────────────────────────────────────
print("[backfill] docs/ADR* → Decisions/...")
adr_patterns = ["ADR*.md", "ADR_*.md"]
for pattern in adr_patterns:
    for adr_file in sorted(DOCS.glob(pattern)):
        try:
            content = adr_file.read_text(encoding="utf-8")
            slug = adr_file.stem.lower().replace("_", "-")
            write_note("Decisions", slug, content, tags=["adr", "decision"])
            counts["adrs"] += 1
            print(f"[backfill]   → {adr_file.name}")
        except Exception as e:
            print(f"[backfill]   SKIP {adr_file.name}: {e}")


# ── 4. Coordination runs → Decisions/  ─────────────────────────────────────
runs_file = DATA / "coordination_runs.jsonl"
if runs_file.exists():
    print("[backfill] coordination_runs.jsonl → Decisions/...")
    with runs_file.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                run_id = r.get("run_id", "?")
                pattern = r.get("pattern", "unknown")
                goal = r.get("goal", "?")[:80]
                slug = f"{pattern}-{run_id}"
                summary = r.get("summary", "")
                score = r.get("final_score", "")
                content = f"# {pattern.title()}: {goal}\n\n"
                if score:
                    content += f"**Score:** {score}\n\n"
                if summary:
                    content += f"## Summary\n{summary}\n"
                write_note("Decisions", slug, content, tags=["coordinator", pattern, "backfill"])
                counts["coordination"] += 1
            except Exception:
                pass
    print(f"[backfill]   → {counts['coordination']} coordination runs mirrored")


# ── 5. Key skill docs → Skills/  ────────────────────────────────────────────
skills_dir = ROOT / ".claude" / "skills"
key_skills = [
    "llm-council-decision",
    "context-first",
    "systematic-debugging",
    "leadgen-ops",
    "fable-operating-manual",
    "production-ready",
    "voice-agent-kb",
    "agent-loop-design",
    "multi-agent-coordination",
]
if skills_dir.exists():
    print("[backfill] .claude/skills/ → Skills/ (key skills)...")
    sk_count = 0
    for skill_name in key_skills:
        for ext in (".md", "/SKILL.md"):
            candidate = (
                skills_dir / (skill_name + ext)
                if ext == ".md"
                else skills_dir / skill_name / "SKILL.md"
            )
            if candidate.exists():
                try:
                    content = candidate.read_text(encoding="utf-8")[:8000]
                    write_note("Skills", skill_name, content, tags=["skill"])
                    sk_count += 1
                    break
                except Exception:
                    pass
    print(f"[backfill]   → {sk_count} skill docs mirrored")


# ── Summary  ────────────────────────────────────────────────────────────────
print("\n[backfill] COMPLETE")
print(f"  Leads:        {counts['leads']}")
print(f"  Memory:       {counts['memory']}")
print(f"  ADRs:         {counts['adrs']}")
print(f"  Coord runs:   {counts['coordination']}")
print(f"\nVault location: {VAULT}")
print("Next: git push from vault dir or wait for nightly obsidian_push job (02:15 IST).")
