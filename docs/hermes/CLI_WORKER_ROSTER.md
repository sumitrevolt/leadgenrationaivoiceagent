# Hermes CLI Bot Workers (SUPERSEDED)

> **Superseded 2026-09-12** by `docs/architecture/24X7_FINAL_DECISION_2026-09-12.md`.
> The canonical bot registry is the **9-bot -> 31-agent** map in
> `docs/architecture/24X7_ARCHITECTURE_RECORD.md` section 4. Of those 9 bots, exactly these **6** run as
> headless **CLI workers** (they carry `ui_meta.hermes-bots.cli_worker`):
>
> `operations` - `engineering` - `platform` - `guardian` - `sales` - `success`
>
> `Pilot` (commander), `board` (owner authority) and `hunter` (specialist lead-gen) are **not** CLI workers.
> See the FINAL DECISION doc for the full mapping. This file is kept only as a pointer.
