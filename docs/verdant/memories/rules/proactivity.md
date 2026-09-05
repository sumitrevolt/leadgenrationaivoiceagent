---

# Task Complexity Signals

## Strong Signals (Single match triggers complex path)

- ~~Cross-project/multi-module coordination (involves 2+ projects or multiple independent modules)~~ **[Downgraded]** See downgrade log
- Involves irreversible operations (database deletion, force push, production environment changes)
- User explicitly requests: "propose a plan first", "do it carefully", "step by step", "confirm before proceeding"
- Involves core system architecture modifications (e.g., Session mechanism, Compression logic, Hook system)
- **Requires cross-compact tracking** — task execution cycle spans multiple session compactions, requiring persistent state and progress

## Weak Signals (Requires 2+ combinations to trigger complex path)

- Single file but complex logic (core business logic modification)
- First task in a new project (unfamiliar with project structure and conventions)
- Ambiguous or vague requirement description
- Involves user preferences but not explicitly stated (e.g., "delete" vs "disable", refer to manager-lessons.md lesson 4)
- **Multiple modules but changes are straightforward in each** — multi-module ≠ complex, the key is whether changes are intuitive
