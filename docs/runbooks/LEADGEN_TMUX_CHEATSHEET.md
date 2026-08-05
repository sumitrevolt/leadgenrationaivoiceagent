# LeadGen tmux Cockpit — Cheat Sheet (MSYS2)

## Launch / band karna
- **Doctor:** PowerShell me `.\leadgen-operator-doctor.ps1` run karo. Ye MSYS2, tmux, Git SSH, key, Graphify, script syntax, aur VPS compose reachability check karta hai.
- **Start:** repo root me `leadgen-tmux.bat` double-click. `leadgen` session (6 windows) me attach ho jayega.
- **Detach (background me chhodo):** `Ctrl-Space` phir `d`. Session chalti rehti hai.
- **Reattach:** naye MSYS2 window me `tmux attach -t leadgen` (ya dobara `.bat`).
- **Poori session band:** `tmux kill-session -t leadgen`.

> **Prefix key = `Ctrl-Space`**. Jo command "prefix" maange, pehle `Ctrl-Space` dabao-chhodo, phir agla key.

## 6 windows — ab har ek REAL kaam karta hai
| # | Window | Launch pe | Note |
|---|--------|-----------|------|
| 1 | architect  | **auto**: `git status -sb` + last 6 commits | read-only git dashboard |
| 2 | backend    | command **ready** (Enter dabao): `uvicorn app.main:app --reload` | DB/Redis VPS pe → local degraded ho sakta |
| 3 | automation | **auto**: live VPS worker logs stream (Ctrl-C = stop) | app/scheduler: `bash leadgen-vps.sh logs app` |
| 4 | tests      | **ready**: targeted fast suite (`billing_truth + test_api`) | full suite `pytest tests/` HANG hota — targeted use karo |
| 5 | voice      | **ready**: `python scripts/agent_tester.py` | voice scorecard |
| 6 | monitor    | **L pane auto**: VPS containers · **R pane ready**: public /health loop | live prod status |

- **"auto"** = launch pe khud chal gaya. **"ready"** = command type ho ke prompt pe hai, aap sirf **Enter** dabao.

## VPS helper — `leadgen-vps.sh` (monitoring-first)
Kisi bhi window me:
```
bash leadgen-vps.sh ps                 # saare containers + health
bash leadgen-vps.sh logs worker        # worker logs (ya app|worker-heavy|scheduler|redis)
bash leadgen-vps.sh applogs            # app container logs
bash leadgen-vps.sh health             # VPS internal /health
bash leadgen-vps.sh ssh                # VPS pe SSH shell (deploy runbook ke bina change mat karo)
```
Connection: `root@72.61.245.204`, Git-ssh + `~/.ssh/id_rsa`. Default commands monitoring-only hain; deploy alag guarded runbook se hota hai.

## Windows switch
- **`Alt-1` .. `Alt-6`** → us window pe. `Ctrl-Space n`/`p` = next/prev. Status bar naam pe mouse-click bhi.

## Panes (split)
- Vertical: `Ctrl-Space` phir `%` · Horizontal: `Ctrl-Space` phir `"`
- Move: **`Alt-arrow`** · Resize: **`Alt-Shift-arrow`** · Band: `exit` ya `Ctrl-Space x`
- monitor window pehle se 2 panes me split hai.

## Useful
- Copy/scroll mode: `Ctrl-Space` phir `[` (arrows/PageUp, `q` exit). Mouse scroll bhi on.
- Window rename `Ctrl-Space ,` · Naya window `Ctrl-Space c`
- **Paste is window me `Ctrl+V` NAHI** — **right-click** ya **Shift+Insert**.

## Files (repo root)
- `leadgen-tmux.bat` — launcher (double-click). MSYS2 `-use-full-path` se Windows git/node/python bhi milte hain.
- `leadgen-tmux-setup.sh` — cockpit banata hai + `~/.tmux.conf`. Windows/commands yahi se edit.
- `leadgen-vps.sh` — VPS monitoring-first helper.
- `leadgen-operator-doctor.ps1` — setup verification / missing dependency finder.

## Notes
- Ye **MSYS2** pe chal raha hai (WSL me distro nahi tha). Local: git/python(.venv 3.11.9)/node ready.
- Prod stack (app/worker/db/redis/qdrant + ~35 containers) **VPS pe live & healthy** — automation/monitor wahi se pull karte hain.
- Config badla to `.bat` dobara chalao (session kill + fresh).
