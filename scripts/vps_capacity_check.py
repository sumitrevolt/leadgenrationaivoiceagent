#!/usr/bin/env python3
"""VPS capacity check for the OPTIONAL heavy voice deps (Silero VAD + Smart Turn).

WHAT THIS DOES (and does NOT do)
--------------------------------
Voice latency/quality can be upgraded with two free, CPU-only models:
  * silero-vad  -> robust speech gate (filters ambient noise/echo)     [USE_SILERO_VAD=1]
  * pipecat-ai  -> Smart Turn v3 semantic end-of-turn (no mid-sentence cut) [USE_SMART_TURN=1]

Both pull **torch** (~800 MB-1 GB on disk, ~300-600 MB RAM at load). On a small
live VPS that can OOM-kill uvicorn or fill the disk. So this script ONLY:
  1. measures free RAM, free disk (on the install partition) and CPU count,
  2. prints a SAFE / TIGHT / UNSAFE verdict against conservative thresholds,
  3. PRINTS the exact pip + env commands for YOU to run by hand if SAFE.

It NEVER installs anything and never touches torch/silero/pipecat. Pure stdlib —
runs anywhere (Linux VPS, Windows dev). On the VPS run:

    cd /opt/leadgen && python scripts/vps_capacity_check.py
    # or against the venv:  .venv/bin/python scripts/vps_capacity_check.py

Exit code: 0 = SAFE, 1 = TIGHT (proceed only after freeing room / swap), 2 = UNSAFE.

Thresholds (conservative, override via env if you know your box):
    VPS_MIN_FREE_RAM_MB   default 1200   (torch load headroom + uvicorn workers)
    VPS_MIN_FREE_DISK_MB  default 2500   (torch wheels + onnx models + pip cache)
    VPS_MIN_CPU           default 2       (ONNX inference + the existing call loop)
"""

from __future__ import annotations

import os
import shutil
import sys

# Install partition we care about: where /opt/leadgen (the app) lives if present,
# else the current working dir's filesystem.
_INSTALL_DIR = "/opt/leadgen" if os.path.isdir("/opt/leadgen") else os.getcwd()


def _int_env(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, "") or default))
    except Exception:
        return default


MIN_FREE_RAM_MB = _int_env("VPS_MIN_FREE_RAM_MB", 1200)
MIN_FREE_DISK_MB = _int_env("VPS_MIN_FREE_DISK_MB", 2500)
MIN_CPU = _int_env("VPS_MIN_CPU", 2)


def _free_ram_mb() -> float | None:
    """Available RAM in MB. Prefers /proc/meminfo MemAvailable (Linux); falls
    back to psutil if present; None if neither works (e.g. Windows w/o psutil)."""
    # 1) Linux /proc/meminfo — most accurate, no deps.
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            info = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    info[parts[0].strip()] = parts[1].strip()
        avail_kb = info.get("MemAvailable")
        if avail_kb:
            return int(avail_kb.split()[0]) / 1024.0
        # older kernels: approximate from MemFree + Buffers + Cached
        free = int((info.get("MemFree") or "0").split()[0])
        buf = int((info.get("Buffers") or "0").split()[0])
        cache = int((info.get("Cached") or "0").split()[0])
        if free or buf or cache:
            return (free + buf + cache) / 1024.0
    except Exception:
        pass
    # 2) psutil fallback (optional)
    try:
        import psutil  # type: ignore

        return psutil.virtual_memory().available / (1024.0 * 1024.0)
    except Exception:
        return None


def _total_ram_mb() -> float | None:
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    try:
        import psutil  # type: ignore

        return psutil.virtual_memory().total / (1024.0 * 1024.0)
    except Exception:
        return None


def _free_disk_mb(path: str) -> float | None:
    try:
        usage = shutil.disk_usage(path)
        return usage.free / (1024.0 * 1024.0)
    except Exception:
        return None


def _cpu_count() -> int:
    try:
        return os.cpu_count() or 1
    except Exception:
        return 1


def _swap_mb() -> float:
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("SwapTotal:"):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    return 0.0


INSTALL_COMMANDS = """\
# ── INSTALL COMMANDS (run by hand on the VPS, ONLY if the verdict above is SAFE) ──
# Use the app's venv so the running uvicorn picks the libs up. Torch CPU wheel is
# the heavy one — pin the CPU index so you don't pull the ~2 GB CUDA build.

cd /opt/leadgen

# 1) torch (CPU-only) + silero-vad  — the speech gate (USE_SILERO_VAD)
.venv/bin/pip install --no-cache-dir \\
    torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install --no-cache-dir silero-vad

# 2) pipecat-ai (bundles smart-turn-v3 ONNX) — semantic end-of-turn (USE_SMART_TURN)
#    onnxruntime comes as a dep; it's light (~15 MB) vs torch.
.venv/bin/pip install --no-cache-dir "pipecat-ai[silero]"

# 3) Enable the flags in /opt/leadgen/.env (systemd EnvironmentFile), then restart:
#    USE_SILERO_VAD=1
#    USE_SMART_TURN=1
#    # optional tuning (defaults shown):
#    # SILERO_VAD_THRESHOLD=0.5   SMART_TURN_THRESHOLD=0.55
#    # TURN_SILENCE_MS=700        TURN_VAD_RMS=300        TURN_BARGE_MIN_MS=100
#
#    systemctl restart leadgen
#
# 4) VERIFY on the FREE web-call FIRST (never first on a paid call):
#    open https://leadsgenai.in/app/test-call  and talk to the agent, OR
#    python scripts/voice_latency_scorecard.py   # p50/p95 turn + TTFT
#    python scripts/agent_tester.py              # double/empty/repeat/slow scorecard
#
# ROLLBACK (instant, no uninstall needed): just remove/0 the flags + restart —
#    USE_SILERO_VAD / USE_SMART_TURN unset => gates return None => RMS/silence
#    fallback => identical to today. The wheels can stay installed harmlessly.
"""


def main() -> int:
    free_ram = _free_ram_mb()
    total_ram = _total_ram_mb()
    free_disk = _free_disk_mb(_INSTALL_DIR)
    cpu = _cpu_count()
    swap = _swap_mb()

    print("=" * 64)
    print(" VPS CAPACITY CHECK — Silero VAD + Smart Turn (torch, heavy/optional)")
    print("=" * 64)
    print(f" Install dir   : {_INSTALL_DIR}")
    print(
        f" RAM           : free {free_ram:.0f} MB"
        + (f" / total {total_ram:.0f} MB" if total_ram else "")
        if free_ram is not None
        else " RAM           : (unknown — no /proc/meminfo, no psutil)"
    )
    print(f" Swap          : {swap:.0f} MB")
    print(
        f" Disk (free)   : {free_disk:.0f} MB"
        if free_disk is not None
        else " Disk (free)   : (unknown)"
    )
    print(f" CPU cores     : {cpu}")
    print("-" * 64)
    print(
        f" Need (min)    : RAM>={MIN_FREE_RAM_MB} MB  Disk>={MIN_FREE_DISK_MB} MB  CPU>={MIN_CPU}"
    )
    print("-" * 64)

    reasons: list[str] = []
    unsafe = False
    tight = False

    # RAM (effective = free + swap, but swap is slow so only counts partially).
    eff_ram = (free_ram or 0.0) + min(swap, 1024.0) * 0.5
    if free_ram is None:
        reasons.append("RAM unknown — measure manually (`free -m`) before installing.")
        tight = True
    elif eff_ram < MIN_FREE_RAM_MB * 0.7:
        reasons.append(
            f"RAM too low ({free_ram:.0f} MB free, +{swap:.0f} MB swap): torch load can OOM-kill uvicorn."
        )
        unsafe = True
    elif eff_ram < MIN_FREE_RAM_MB:
        reasons.append(
            f"RAM tight ({free_ram:.0f} MB free): add swap or install during a low-traffic window."
        )
        tight = True

    # Disk.
    if free_disk is None:
        reasons.append("Disk free unknown — check `df -h /opt/leadgen` before installing.")
        tight = True
    elif free_disk < MIN_FREE_DISK_MB:
        reasons.append(
            f"Disk too low ({free_disk:.0f} MB free): torch wheels alone are ~1 GB. Free space first."
        )
        unsafe = True
    elif free_disk < MIN_FREE_DISK_MB * 1.5:
        reasons.append(
            f"Disk okay but not roomy ({free_disk:.0f} MB) — clear pip cache after install."
        )
        tight = True

    # CPU.
    if cpu < MIN_CPU:
        reasons.append(
            f"Only {cpu} CPU core(s): ONNX inference will compete with the call loop "
            "(Smart Turn may add latency instead of removing it). Prefer Silero-only, or skip."
        )
        tight = True

    if unsafe:
        verdict, code = "UNSAFE — DO NOT INSTALL yet", 2
    elif tight:
        verdict, code = "TIGHT — proceed only after addressing the notes below", 1
    else:
        verdict, code = "SAFE to install (still test on the FREE web-call first)", 0

    print(f" VERDICT       : {verdict}")
    if reasons:
        print("-" * 64)
        for r in reasons:
            print(f"   - {r}")
    print()
    print(INSTALL_COMMANDS)

    if code == 0:
        print(">> Verdict SAFE. The flags stay OFF until you set them — nothing changed yet.")
    elif code == 1:
        print(
            ">> Verdict TIGHT. Address the notes (add swap / free disk / low-traffic window) first."
        )
    else:
        print(">> Verdict UNSAFE. Do NOT run the install commands until capacity improves.")
    return code


if __name__ == "__main__":
    sys.exit(main())
