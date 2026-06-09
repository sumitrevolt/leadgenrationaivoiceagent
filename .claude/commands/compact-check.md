---
description: Decide karo ki compact karein ya nayi chat shuru — LeadGen AI token discipline (strategic compaction).
---
# /compact-check — strategic context management

CLAUDE.md rule: **naya task = naya chat** (memory CLAUDE.md + `docs/SESSION_LOG.md` se persist hoti). Auto-compaction arbitrary point pe context khota hai — better hai LOGICAL boundary pe khud compact/restart karo.

## Naya chat / compact KAB
- **Exploration → execution ke beech**: research context bhaari ho gaya, plan ready hai → compact, plan rakho.
- **Milestone complete hone par**: fresh start next phase ke liye (pehle `/checkpoint`).
- **Bade context-shift se pehle**: alag task = alag chat.
- **Heavy multi-file session lamba + tokens jal rahe**: `/checkpoint` karke naya chat.

## Pehle yeh karo
`/checkpoint` chalao (SESSION_LOG append + commit) taaki nayi chat memory uthaye. CLAUDE.md LEAN rakho (har turn load — bloat = har turn token).

Source idea: strategic-compact (everything-claude-code), project ke liye adapt kiya.
