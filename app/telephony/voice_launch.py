"""voice_launch — controlled outbound-calling launch spine (2026-07-17).

KYUN: cold AI calling (`platform_dial`) 05-Jul se 3-layer HARD OFF tha (real
paisa + IVR ko "interested" mark). Controlled re-launch ke liye ek CENTRAL,
fail-CLOSED safety spine chahiye jo:
  * per-lead eligibility ek jagah decide kare (compliance + dial_gate + consent
    ko compose karke — koi naya compliance gate NAHI, existing chokepoints reuse),
  * daily attempt cap (default 100 IST/day) ATOMIC + cross-worker rakhe,
  * concurrency limit expose kare,
  * 30-call training-pause boundaries bataye,
  * provider dispositions (NUP/busy/failed/rejected/no_answer) canonicalize kare
    aur decide kare kaunsa attempt cap me count hota hai,
  * campaign state machine ke states de.

DESIGN (repo-consistent): import-safe, koi function KABHI raise nahi karta.
Master flag ``VOICE_LAUNCH_CAMPAIGN`` (default OFF = INERT) — is module ke hone
bhar se koi call NAHI lagti; ye sirf gate/counter/state helpers deta hai jinhe
dial loop explicit call kare. platform_dial ke teen kill-layers (env/data-file/
scheduler) is module se untouched hain — ye unke UPAR ek extra safety spine hai.

FAIL-CLOSED: agar counter (Redis) unavailable ho to cap "reached" maana jata hai
(spend/compliance cap ko count na kar paane par dial mat karo). Eligibility me
koi gate prove na ho to lead INELIGIBLE.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from app.telephony.compliance import IST
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Launch hard ceiling — daily cap kabhi is se upar nahi ja sakta (env override bhi clamp).
_DAILY_CAP_CEILING = 100
_DEFAULT_DAILY_CAP = 100
_DEFAULT_TEST_CAP = 25  # internal test calls (allowlist) — campaign quota se ALAG
_DEFAULT_CONCURRENCY = 1
_TRAIN_BATCH = 30  # 30-call batches: pause@30/60/90 → train → resume
_COUNTER_TTL_S = 129600  # 36h — IST-date counter, midnight rollover buffer

# Session-scoped ceiling — exactly VOICE_CALLS_PER_SESSION attempts per launch
# session (default 30). Redis-backed → worker/scheduler restart counter RESET
# NAHI karta; reset sirf canonical create_voice_session() lifecycle se.
_DEFAULT_SESSION_CAP = 30
_SESSION_CAP_CEILING = 200
_SESSION_TTL_S = 7 * 86400  # 7 days — session training-pauses (ghanto tak) span karti hai


# --------------------------------------------------------------------------- #
# Campaign state machine
# --------------------------------------------------------------------------- #
class CampaignState(str, Enum):
    DRAFT = "draft"
    COMPLIANCE_BLOCKED = "compliance_blocked"
    READY = "ready"
    TEST_MODE = "test_mode"
    PILOT = "pilot"
    RUNNING = "running"
    PAUSED_FOR_TRAINING = "paused_for_training"
    PAUSED_BY_ADMIN = "paused_by_admin"
    PAUSED_BY_CIRCUIT_BREAKER = "paused_by_circuit_breaker"
    DAILY_LIMIT_REACHED = "daily_limit_reached"
    SESSION_LIMIT_REACHED = "session_limit_reached"
    SESSION_STOPPED = "session_stopped"
    COMPLETED = "completed"
    FAILED = "failed"


# States in which the dial loop is allowed to place NEW calls.
_DIALABLE_STATES = frozenset({CampaignState.TEST_MODE, CampaignState.PILOT, CampaignState.RUNNING})


def state_is_dialable(state: CampaignState) -> bool:
    return state in _DIALABLE_STATES


# --------------------------------------------------------------------------- #
# Canonical dispositions + counting policy (NUP resolution)
# --------------------------------------------------------------------------- #
class VoiceDisposition(str, Enum):
    """Canonical outbound-attempt disposition.

    NUP resolution (2026-07-17): "NUP" (Number Un-obtainable / Not-UP) codebase
    ke CallOutcome enum me NAHI tha — ye ek PROVIDER/SIP-layer non-connect
    disposition hai (unallocated/unobtainable/rejected number, SIP 3/4/6xx).
    Canonically ise NUP alag rakha hai (billing/analytics visibility ke liye),
    par FAILED family ke saath ek NON-CONNECT attempt hai. Launch policy: har
    provider-ACCEPTED attempt (answered/nup/busy/failed/rejected/no_answer/...)
    daily cap me count hota hai; sirf pre-dial SKIP (gate ne block kiya, call
    kabhi lagi hi nahi) count NAHI hota.
    """

    ANSWERED = "answered"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    REJECTED = "rejected"
    NUP = "nup"
    VOICEMAIL = "voicemail"
    DND = "dnd"
    WRONG_NUMBER = "wrong_number"
    DROPPED = "dropped"
    SKIPPED = "skipped"  # pre-dial gate skip — call NEVER placed, does NOT count


# Raw provider/webhook/internal token -> canonical. Lowercased+stripped lookup.
_DISPOSITION_ALIASES: dict[str, VoiceDisposition] = {
    # answered / connected family
    "answered": VoiceDisposition.ANSWERED,
    "answer": VoiceDisposition.ANSWERED,
    "connected": VoiceDisposition.ANSWERED,
    "completed": VoiceDisposition.ANSWERED,
    "complete": VoiceDisposition.ANSWERED,
    "hangup": VoiceDisposition.ANSWERED,
    "interested": VoiceDisposition.ANSWERED,
    "appointment": VoiceDisposition.ANSWERED,
    "callback": VoiceDisposition.ANSWERED,
    "not_interested": VoiceDisposition.ANSWERED,
    # Vobiz HangupCause tokens (live 2026-07-17)
    "normal_clearing": VoiceDisposition.ANSWERED,
    "end_of_xml_instructions": VoiceDisposition.ANSWERED,
    # no-answer family
    "no_answer": VoiceDisposition.NO_ANSWER,
    "no-answer": VoiceDisposition.NO_ANSWER,
    "noanswer": VoiceDisposition.NO_ANSWER,
    "no_user_response": VoiceDisposition.NO_ANSWER,
    "missed": VoiceDisposition.NO_ANSWER,
    "ring_timeout": VoiceDisposition.NO_ANSWER,
    "timeout": VoiceDisposition.NO_ANSWER,
    # busy
    "busy": VoiceDisposition.BUSY,
    "user_busy": VoiceDisposition.BUSY,
    # NUP — number unobtainable / unallocated / not-up (SIP 404/410/604/3xx)
    "nup": VoiceDisposition.NUP,
    "unobtainable": VoiceDisposition.NUP,
    "unallocated": VoiceDisposition.NUP,
    "unallocated_number": VoiceDisposition.NUP,
    "number_unobtainable": VoiceDisposition.NUP,
    "not_up": VoiceDisposition.NUP,
    "invalid_number": VoiceDisposition.NUP,
    "invalid": VoiceDisposition.NUP,
    "congestion": VoiceDisposition.NUP,
    "network_unreachable": VoiceDisposition.NUP,
    # rejected / declined
    "rejected": VoiceDisposition.REJECTED,
    "declined": VoiceDisposition.REJECTED,
    "call_rejected": VoiceDisposition.REJECTED,
    "forbidden": VoiceDisposition.REJECTED,
    # failed (generic provider failure that still consumed an attempt)
    "failed": VoiceDisposition.FAILED,
    "error": VoiceDisposition.FAILED,
    # voicemail / machine
    "voicemail": VoiceDisposition.VOICEMAIL,
    "machine": VoiceDisposition.VOICEMAIL,
    "amd": VoiceDisposition.VOICEMAIL,
    # compliance / data quality
    "dnd": VoiceDisposition.DND,
    "opt_out": VoiceDisposition.DND,
    "wrong_number": VoiceDisposition.WRONG_NUMBER,
    "dropped": VoiceDisposition.DROPPED,
    # pre-dial skip
    "skipped": VoiceDisposition.SKIPPED,
    "skip": VoiceDisposition.SKIPPED,
    "blocked": VoiceDisposition.SKIPPED,
}

# Dispositions that DO NOT count toward the daily cap (call never placed).
_NON_COUNTING = frozenset({VoiceDisposition.SKIPPED})
# Dispositions that represent a live human connection.
_CONNECT = frozenset({VoiceDisposition.ANSWERED})


def normalize_disposition(raw: Any) -> VoiceDisposition:
    """Map any raw provider/internal status token to a canonical VoiceDisposition.
    Unknown => FAILED (conservative: a provider-accepted-but-unknown attempt still
    counts toward the cap rather than being silently ignored). Never raises."""
    try:
        if isinstance(raw, VoiceDisposition):
            return raw
        key = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
        if not key:
            return VoiceDisposition.FAILED
        return _DISPOSITION_ALIASES.get(key, VoiceDisposition.FAILED)
    except Exception:
        return VoiceDisposition.FAILED


def disposition_counts_toward_cap(disp: Any) -> bool:
    """Launch policy: har provider-accepted attempt counts; sirf pre-dial SKIP nahi."""
    return normalize_disposition(disp) not in _NON_COUNTING


def disposition_is_connect(disp: Any) -> bool:
    return normalize_disposition(disp) in _CONNECT


# --------------------------------------------------------------------------- #
# Structured skip reasons (why a lead is ineligible)
# --------------------------------------------------------------------------- #
class SkipReason:
    NONE = ""
    NO_PHONE = "no_phone"
    INVALID_PHONE = "invalid_phone"
    ADMIN_KILL = "admin_kill_switch"
    CAMPAIGN_DISABLED = "campaign_disabled"
    DIAL_TEST_MODE = "dial_test_mode_not_allowlisted"
    PHONE_TYPE_BLOCKED = "phone_type_blocked"
    LEARNED_IVR_BLOCK = "learned_ivr_block"
    ON_DND = "on_dnd_registry"
    DND_LOOKUP_FAILED = "dnd_lookup_failed"
    OPTED_OUT = "opted_out"
    OUTSIDE_WINDOW = "outside_calling_window"
    DLT_NOT_APPROVED = "dlt_not_approved"
    NO_CALLER_ID = "no_caller_id"
    COMPLIANCE_DISABLED = "compliance_disabled_unsafe"
    GATE_ERROR = "gate_error"


@dataclass
class EligibilityResult:
    eligible: bool
    reason: str = SkipReason.NONE
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"eligible": self.eligible, "reason": self.reason, "detail": dict(self.detail)}


# --------------------------------------------------------------------------- #
# Config knobs (env-first; read at call-time so VPS toggle needs no code deploy)
# --------------------------------------------------------------------------- #
def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name, "") or "").strip() or default


def _flag_on(name: str, default: bool = False) -> bool:
    v = _env(name).lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def campaign_enabled() -> bool:
    """Master gate. Default OFF = INERT (dial loop must no-op). platform_dial ke
    teen kill-layers ke UPAR ek aur explicit launch gate."""
    return _flag_on("VOICE_LAUNCH_CAMPAIGN", default=False)


def _kill_file() -> Path:
    """Resolved per call, never captured at import.

    The runtime-data cutover can move this store to the external root; a path
    frozen at import could never follow it. VOICE_LAUNCH_KILL_FILE keeps its
    current precedence before the cutover, and after it the authority refuses an
    override that points anywhere but the canonical target — a forgotten
    `VOICE_LAUNCH_KILL_FILE=data/...` must not route an emergency control back
    into a checkout a deploy can reset.

    This may RAISE (stale override after cutover). Every caller treats that as
    INVALID_PATH, which engages the kill: an unresolvable authority is exactly
    the case where dialling must not proceed.
    """
    from app.platform import runtime_data_authority as _auth

    return _auth.resolve_store_path(
        store_id="telephony.voice_kill_switch",
        legacy_path=Path("data/voice_launch_kill.json"),
        target_segments=("telephony", "voice_launch_kill.json"),
        override_env="VOICE_LAUNCH_KILL_FILE",
    )


@dataclass(frozen=True)
class AdminKillStatus:
    """Kill decision plus WHY, with no raw value in it.

    Deliberately has no ``__bool__``: `owner_os` wraps the old call in
    ``bool(...)``, so a status object leaking into that position would report
    "engaged" forever. Engagement must be read from ``.engaged``.
    """

    engaged: bool
    source: str
    reason: str


_KILL_TRUE = ("1", "true", "yes", "on")
_KILL_FALSE = ("0", "false", "no", "off")


def _kill_file_status() -> AdminKillStatus:
    """File fallback. EVERY failure engages the kill.

    An emergency switch whose file went missing must not read as "disengaged" —
    that is how a deploy that resets the checkout silently re-arms dialling.
    """
    from app.platform import runtime_data as _rd

    try:
        p = _kill_file()
    except Exception:
        return AdminKillStatus(True, "FILE", "INVALID_PATH")

    if _rd.is_production():
        try:
            if not p.is_absolute():
                return AdminKillStatus(True, "FILE", "INVALID_PATH")
            # Symlink-aware: resolve() before the containment test, so a link
            # pointing back into the checkout cannot wear a disguise.
            resolved = p.resolve()
            if _rd._is_inside(resolved, _rd._repo_root()):
                return AdminKillStatus(True, "FILE", "OUTSIDE_RUNTIME_ROOT")
            if resolved.exists() and not resolved.is_file():
                return AdminKillStatus(True, "FILE", "INVALID_PATH")
        except Exception:
            return AdminKillStatus(True, "FILE", "INVALID_PATH")

    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return AdminKillStatus(True, "FILE", "MISSING")
    except (PermissionError, OSError):
        return AdminKillStatus(True, "FILE", "UNREADABLE")
    except Exception:
        return AdminKillStatus(True, "FILE", "UNREADABLE")

    try:
        data = json.loads(raw)
    except Exception:
        return AdminKillStatus(True, "FILE", "MALFORMED")

    # STRICT: a real bool only. `bool(data.get("kill"))` accepted {"kill": 1}
    # and {"kill": "false"} — a safety switch cannot run on truthiness.
    # isinstance is exact here: isinstance(1, bool) is False, so the integer
    # payloads that truthiness used to accept still fail.
    if not isinstance(data, dict) or not isinstance(data.get("kill"), bool):
        return AdminKillStatus(True, "FILE", "INVALID_SCHEMA")

    if data["kill"]:
        return AdminKillStatus(True, "FILE", "FILE_ENGAGED")
    return AdminKillStatus(False, "FILE", "FILE_DISENGAGED")


def admin_kill_status() -> AdminKillStatus:
    """Global admin kill switch, fail-CLOSED, with a non-secret reason.

    ENV ``VOICE_LAUNCH_KILL`` is FINAL when it carries a recognised token; the
    data-file is only the fallback (container-recreate ke bina flip — data/
    bind-mount). A non-empty UNRECOGNISED token engages rather than falling
    through, because "VOICE_LAUNCH_KILL=maybe" is a misconfiguration, not a
    licence to dial.
    """
    v = _env("VOICE_LAUNCH_KILL").strip().lower()
    if v in _KILL_TRUE:
        return AdminKillStatus(True, "ENV", "ENV_ENGAGED")
    if v in _KILL_FALSE:
        return AdminKillStatus(False, "ENV", "ENV_DISENGAGED")
    if v:
        return AdminKillStatus(True, "ENV", "INVALID_ENV_VALUE")
    return _kill_file_status()


def admin_kill_engaged() -> bool:
    """Boolean wrapper — the three execution call sites keep a real bool."""
    return admin_kill_status().engaged


def daily_cap(kind: str = "campaign") -> int:
    """Attempts/IST-day ceiling. campaign default 100 (hard-clamped ≤100),
    test allowlist default 25 (separate quota)."""
    if kind == "test":
        try:
            n = int(_env("VOICE_TEST_DAILY_CAP", str(_DEFAULT_TEST_CAP)))
        except Exception:
            n = _DEFAULT_TEST_CAP
        return max(1, min(n, 200))
    try:
        n = int(_env("VOICE_DAILY_CALL_CAP", str(_DEFAULT_DAILY_CAP)))
    except Exception:
        n = _DEFAULT_DAILY_CAP
    return max(1, min(n, _DAILY_CAP_CEILING))


def session_cap() -> int:
    """Per-SESSION attempt ceiling — ``VOICE_CALLS_PER_SESSION`` (default 30,
    hard-clamped ≤200). One session = one operator launch (create_voice_session);
    counter Redis-backed (worker/scheduler restart = NO reset). Sirf canonical
    session lifecycle counter ko reset karta hai."""
    try:
        n = int(_env("VOICE_CALLS_PER_SESSION", str(_DEFAULT_SESSION_CAP)))
    except Exception:
        n = _DEFAULT_SESSION_CAP
    return max(1, min(n, _SESSION_CAP_CEILING))


def concurrency_limit() -> int:
    try:
        n = int(_env("VOICE_CALL_CONCURRENCY", str(_DEFAULT_CONCURRENCY)))
    except Exception:
        n = _DEFAULT_CONCURRENCY
    return max(1, min(n, 10))


def training_batch_size() -> int:
    try:
        n = int(_env("VOICE_TRAIN_BATCH", str(_TRAIN_BATCH)))
    except Exception:
        n = _TRAIN_BATCH
    return max(5, min(n, 100))


# --------------------------------------------------------------------------- #
# 30-call training-pause boundaries
# --------------------------------------------------------------------------- #
def training_pause_due(count_after: int) -> bool:
    """True jab abhi-abhi liya gaya attempt ek training boundary pe land kare
    (batch=30 => 30/60/90 ...). Dial loop is boundary pe PAUSED_FOR_TRAINING me
    jaaye, gates chalaye, phir resume kare. Last batch (== cap) pe EOD eval."""
    try:
        b = training_batch_size()
        return count_after > 0 and count_after % b == 0
    except Exception:
        return False


def next_training_boundary(count_so_far: int) -> int | None:
    try:
        b = training_batch_size()
        cap = daily_cap("campaign")
        nxt = ((count_so_far // b) + 1) * b
        return nxt if nxt <= cap else None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Atomic IST daily counter (cross-worker via Redis; fail-CLOSED)
# --------------------------------------------------------------------------- #
def _ist_date() -> str:
    return datetime.now(IST).strftime("%Y%m%d")


def _counter_key(kind: str) -> str:
    return f"voice_launch:attempts:{kind}:{_ist_date()}"


@dataclass
class SlotReservation:
    ok: bool
    count: int
    cap: int
    reason: str = ""


async def _redis():
    from app.cache import get_redis_client

    return await get_redis_client()


async def attempts_today(kind: str = "campaign") -> int:
    """Aaj (IST) ke reserved attempts. Counter unavailable => -1 (unknown)."""
    try:
        r = await _redis()
        raw = await r.get(_counter_key(kind))
        return int(raw) if raw is not None else 0
    except Exception as e:
        logger.warning(f"[voice_launch] attempts_today counter unavailable ({e})")
        return -1


async def daily_cap_reached(kind: str = "campaign") -> bool:
    """FAIL-CLOSED: counter unavailable (-1) => True (block)."""
    n = await attempts_today(kind)
    if n < 0:
        return True
    return n >= daily_cap(kind)


async def reserve_call_slot(kind: str = "campaign") -> SlotReservation:
    """Atomically claim ONE attempt slot for today (IST). Returns ok=False if the
    cap is reached OR the counter is unavailable (fail-CLOSED — spend/compliance
    cap ko count na kar paane par dial mat karo). Idempotency is the CALLER's job
    (dedupe per lead); this only enforces the volume ceiling.

    ATOMICITY: single Redis INCR — multi-worker safe. First incr sets the 36h TTL.
    """
    cap = daily_cap(kind)
    try:
        r = await _redis()
        key = _counter_key(kind)
        count = int(await r.incr(key))
        if count == 1:
            try:
                await r.expire(key, _COUNTER_TTL_S)
            except Exception:
                pass
        if count > cap:
            # over-cap: roll back our own increment so a rejected reservation does
            # not permanently inflate the counter, then report daily_limit_reached.
            try:
                await r.set(key, str(cap), ex=_COUNTER_TTL_S)
            except Exception:
                pass
            return SlotReservation(False, cap, cap, reason="daily_limit_reached")
        return SlotReservation(True, count, cap)
    except Exception as e:
        logger.warning(f"[voice_launch] reserve_call_slot fail-CLOSED ({e})")
        return SlotReservation(False, -1, cap, reason="counter_unavailable")


# --------------------------------------------------------------------------- #
# Centralized per-lead eligibility (fail-CLOSED) — composes existing chokepoints
# --------------------------------------------------------------------------- #
async def is_lead_eligible_for_voice_call(
    phone: str,
    call_type: str = "promotional",
    *,
    now: datetime | None = None,
    lead: Any = None,
) -> EligibilityResult:
    """THE single per-lead pre-dial gate. Fail-CLOSED for promotional calls.

    Composition order (cheapest/most-decisive first):
      1. admin kill switch  -> ineligible
      2. phone presence/sanity
      3. dial_gate.check (test-mode allowlist + phone-type + learned IVR blocklist)
      4. compliance gate (DND fail-closed + calling window + DLT/140 + consent opt-out)

    Ye koi NAYA compliance gate NAHI banata — existing ``app.telephony.compliance``
    aur ``app.telephony.dial_gate`` ko reuse karta hai (single source of truth).
    Never raises. Any internal error => promotional ineligible, transactional eligible.
    """
    ct = (call_type or "promotional").strip().lower()
    detail: dict[str, Any] = {"call_type": ct}
    try:
        # 1) global admin kill switch (fail-safe)
        if admin_kill_engaged():
            return EligibilityResult(False, SkipReason.ADMIN_KILL, detail)

        # 2) phone sanity
        digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
        detail["digits"] = len(digits)
        if not digits:
            return EligibilityResult(False, SkipReason.NO_PHONE, detail)
        if not (10 <= len(digits) <= 15):
            return EligibilityResult(False, SkipReason.INVALID_PHONE, detail)

        # 3) dial_gate — promotional test-mode allowlist + phone-type + learned block
        try:
            from app.telephony import dial_gate

            allowed, reason = dial_gate.check(phone, call_type=ct)
            detail["dial_gate"] = reason
            if not allowed:
                r = SkipReason.DIAL_TEST_MODE
                if reason.startswith("dial_blocklist"):
                    r = SkipReason.LEARNED_IVR_BLOCK
                elif reason.startswith("phone_type_gate"):
                    r = SkipReason.PHONE_TYPE_BLOCKED
                return EligibilityResult(False, r, detail)
        except Exception as e:
            logger.warning(f"[voice_launch] dial_gate error, fail-closed ({e})")
            if ct == "promotional":
                return EligibilityResult(False, SkipReason.GATE_ERROR, detail)

        # 4) compliance gate — THE TRAI chokepoint (DND/window/DLT/consent)
        from app.telephony.compliance import CallType, get_compliance_gate

        ctype = CallType.PROMOTIONAL if ct == "promotional" else CallType.TRANSACTIONAL
        decision = await get_compliance_gate().check(phone, ctype, now=now)
        detail["compliance"] = decision.as_dict()
        if not decision.allowed:
            reason = _map_compliance_reason(decision.reasons)
            return EligibilityResult(False, reason, detail)

        # compliance_disabled bypass is itself a red flag — surface as unsafe.
        if "compliance_disabled" in (decision.reasons or []):
            return EligibilityResult(False, SkipReason.COMPLIANCE_DISABLED, detail)

        return EligibilityResult(True, SkipReason.NONE, detail)
    except Exception as e:
        logger.warning(f"[voice_launch] eligibility error, fail-closed ({e})")
        detail["error"] = str(e)
        safe = ct != "promotional"
        return EligibilityResult(safe, SkipReason.GATE_ERROR, detail)


def _map_compliance_reason(reasons: list[str]) -> str:
    joined = " ".join(reasons or [])
    if "opted_out" in joined:
        return SkipReason.OPTED_OUT
    if "on_dnd_registry" in joined:
        return SkipReason.ON_DND
    if "dnd_lookup_failed" in joined:
        return SkipReason.DND_LOOKUP_FAILED
    if "outside_calling_hours" in joined:
        return SkipReason.OUTSIDE_WINDOW
    if "dlt_not_approved" in joined:
        return SkipReason.DLT_NOT_APPROVED
    if "no_caller_id" in joined:
        return SkipReason.NO_CALLER_ID
    if "invalid_number" in joined:
        return SkipReason.INVALID_PHONE
    return SkipReason.GATE_ERROR


async def release_call_slot(kind: str = "campaign") -> int:
    """Roll back ONE reserved slot (call reserved but NEVER became a provider-accepted
    attempt — e.g. provider-side compliance_blocked). DECR, floored at 0. Never raises."""
    try:
        r = await _redis()
        key = _counter_key(kind)
        cur = await r.get(key)
        n = int(cur) if cur is not None else 0
        n = max(0, n - 1)
        await r.set(key, str(n), ex=_COUNTER_TTL_S)
        return n
    except Exception as e:
        logger.warning(f"[voice_launch] release_call_slot noop ({e})")
        return -1


# --------------------------------------------------------------------------- #
# Session-scoped call limiter (exactly VOICE_CALLS_PER_SESSION per session)
# --------------------------------------------------------------------------- #
# Session = one operator launch (create_voice_session). Counter Redis-backed →
# worker/scheduler restart RESET nahi karta; reset SIRF canonical lifecycle se.
_SESSION_CURRENT_KEY = "voice_launch:session:current"


def _session_meta_key(sid: str) -> str:
    return f"voice_launch:session:{sid}:meta"


def _session_counter_key(sid: str) -> str:
    return f"voice_launch:session:{sid}:attempts"


def _session_stopped_key(sid: str) -> str:
    return f"voice_launch:session:{sid}:stopped"


def _session_disp_key(sid: str, disp: VoiceDisposition) -> str:
    return f"voice_launch:session:{sid}:disp:{disp.value}"


def _session_retried_key(sid: str) -> str:
    return f"voice_launch:session:{sid}:retried"


def _session_idem_key(sid: str, key: str) -> str:
    return f"voice_launch:session:{sid}:idem:{key}"


def new_session_id() -> str:
    try:
        import uuid

        return f"S{datetime.now(IST).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    except Exception:
        return f"S{datetime.now(IST).strftime('%Y%m%d')}-{int(datetime.now().timestamp())}"


async def create_voice_session(owner: str = "", niche: str = "", label: str = "") -> str:
    """Canonical session LIFECYCLE — naya session banao (attempt counter 0 se).
    YAHI single place hai jahan session attempt-count reset hota hai; worker or
    scheduler restart kabhi reset NAHI karta. Never raises (Redis down => "")."""
    try:
        sid = new_session_id()
        r = await _redis()
        meta = json.dumps(
            {
                "sid": sid,
                "owner": (owner or "").strip() or "admin",
                "niche": (niche or "").strip(),
                "label": (label or "").strip(),
                "cap": session_cap(),
                "created_at": datetime.now(IST).isoformat(timespec="seconds"),
            }
        )
        await r.set(_session_meta_key(sid), meta, ex=_SESSION_TTL_S)
        await r.set(_SESSION_CURRENT_KEY, sid, ex=_SESSION_TTL_S)
        # Explicit SET (not INCR) — pichhle session ka stale 30 kabhi leak na ho.
        await r.set(_session_counter_key(sid), "0", ex=_SESSION_TTL_S)
        await r.delete(_session_stopped_key(sid))
        return sid
    except Exception as e:
        logger.warning(f"[voice_launch] create_voice_session failed ({e})")
        return ""


async def current_session_id() -> str | None:
    try:
        r = await _redis()
        v = await r.get(_SESSION_CURRENT_KEY)
        return str(v) if v else None
    except Exception:
        return None


async def get_session_meta(sid: str) -> dict[str, Any]:
    try:
        r = await _redis()
        raw = await r.get(_session_meta_key(sid))
        if not raw:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def session_attempts(sid: str) -> int:
    """Is session me kitne provider-attempts reserve hue. Unknown (-1) = fail-CLOSED."""
    try:
        r = await _redis()
        raw = await r.get(_session_counter_key(sid))
        return int(raw) if raw is not None else 0
    except Exception:
        return -1


async def session_is_stopped(sid: str | None = None) -> bool:
    """Emergency-stop flag. Never raises; no-session/Redis-down => True (fail-closed)."""
    if not sid:
        sid = await current_session_id()
        if not sid:
            return True
    try:
        r = await _redis()
        return bool(await r.get(_session_stopped_key(sid)))
    except Exception:
        return True


async def session_stop(sid: str | None = None) -> bool:
    """Session-level emergency stop — future reservations blocked (in-flight call
    completes). Returns success. Never raises."""
    try:
        r = await _redis()
        if not sid:
            sid = await current_session_id()
        if not sid:
            return False
        await r.set(_session_stopped_key(sid), "1", ex=_SESSION_TTL_S)
        await set_campaign_state(CampaignState.SESSION_STOPPED)
        return True
    except Exception as e:
        logger.warning(f"[voice_launch] session_stop failed ({e})")
        return False


async def reserve_session_slot(sid: str | None = None) -> SlotReservation:
    """Atomically claim ONE provider-attempt slot for the current session.

    ATOMIC (single Redis INCR, multi-worker safe) + FAIL-CLOSED. Blocks:
      * cap+1 (attempt 31)  -> reason='session_limit_reached'
      * emergency stop      -> reason='session_stopped'
      * no active session   -> reason='no_session'
      * Redis unavailable   -> reason='counter_unavailable'
    Over-cap increment rollback hota hai (counter cap pe pin). Reservation = call
    dispatch-boundary se PEHLE hona chahiye (attempt counted sirf jab provider
    request actually jayega)."""
    cap = session_cap()
    if not sid:
        sid = await current_session_id()
        if not sid:
            return SlotReservation(False, -1, cap, reason="no_session")
    try:
        r = await _redis()
        if bool(await r.get(_session_stopped_key(sid))):
            return SlotReservation(False, cap, cap, reason="session_stopped")
        key = _session_counter_key(sid)
        count = int(await r.incr(key))
        if count == 1:
            try:
                await r.expire(key, _SESSION_TTL_S)
            except Exception:
                pass
        if count > cap:
            try:
                await r.set(key, str(cap), ex=_SESSION_TTL_S)
            except Exception:
                pass
            return SlotReservation(False, cap, cap, reason="session_limit_reached")
        return SlotReservation(True, count, cap)
    except Exception as e:
        logger.warning(f"[voice_launch] reserve_session_slot fail-CLOSED ({e})")
        return SlotReservation(False, -1, cap, reason="counter_unavailable")


async def release_session_slot(sid: str | None = None) -> int:
    """Roll back ONE reserved session slot (reserved but NEVER provider-accepted).
    DECR floored at 0. Never raises."""
    try:
        r = await _redis()
        if not sid:
            sid = await current_session_id()
        if not sid:
            return -1
        key = _session_counter_key(sid)
        cur = await r.get(key)
        n = max(0, (int(cur) if cur is not None else 0) - 1)
        await r.set(key, str(n), ex=_SESSION_TTL_S)
        return n
    except Exception as e:
        logger.warning(f"[voice_launch] release_session_slot noop ({e})")
        return -1


async def record_session_disposition(sid: str | None, disp: Any) -> None:
    """Per-session disposition tally (answered/no_answer/busy/failed/nup/...).
    Best-effort; never blocks the caller."""
    try:
        d = normalize_disposition(disp)
        r = await _redis()
        if not sid:
            sid = await current_session_id()
        if not sid:
            return
        key = _session_disp_key(sid, d)
        n = int(await r.incr(key))
        if n == 1:
            try:
                await r.expire(key, _SESSION_TTL_S)
            except Exception:
                pass
    except Exception:
        pass


async def session_disposition_counts(sid: str | None = None) -> dict[str, int]:
    """{disposition: count} for the session. Missing counter => 0. Never raises."""
    out: dict[str, int] = {}
    try:
        r = await _redis()
        if not sid:
            sid = await current_session_id()
        if not sid:
            return out
        for d in VoiceDisposition:
            try:
                raw = await r.get(_session_disp_key(sid, d))
                if raw is not None and int(raw) > 0:
                    out[d.value] = int(raw)
            except Exception:
                continue
    except Exception:
        pass
    return out


async def record_session_retry_blocked(sid: str | None) -> None:
    """Duplicate-dispatch counter (idempotency claim already held) — 'retried'
    calls count ALAG se. Best-effort."""
    try:
        r = await _redis()
        if not sid:
            sid = await current_session_id()
        if not sid:
            return
        key = _session_retried_key(sid)
        n = int(await r.incr(key))
        if n == 1:
            try:
                await r.expire(key, _SESSION_TTL_S)
            except Exception:
                pass
    except Exception:
        pass


async def session_retried(sid: str) -> int:
    try:
        r = await _redis()
        raw = await r.get(_session_retried_key(sid))
        return int(raw) if raw is not None else 0
    except Exception:
        return 0


async def session_idem_claim(sid: str | None, key: str, ttl_s: int = 86400) -> bool:
    """Idempotency claim: True jab is session me is dispatch-key ka provider request
    PEHLI baar ho raha hai. Redis SET NX EX — worker retry/restart survive karta
    hai (double provider request kabhi nahi). False = already dispatched (retry).
    Never raises (Redis down => False = fail-closed)."""
    try:
        r = await _redis()
        if not sid:
            sid = await current_session_id()
        if not sid:
            return False
        got = await r.set(_session_idem_key(sid, key), "1", nx=True, ex=ttl_s)
        return bool(got)
    except Exception as e:
        logger.warning(f"[voice_launch] session_idem_claim fail-CLOSED ({e})")
        return False


async def session_idem_release(sid: str | None, key: str) -> None:
    """Release a claim for a lead that was NEVER dispatched (pre-dial block) so a
    future retry is allowed. Best-effort."""
    try:
        r = await _redis()
        if not sid:
            sid = await current_session_id()
        if not sid:
            return
        await r.delete(_session_idem_key(sid, key))
    except Exception:
        pass


async def session_status(sid: str | None = None) -> dict[str, Any]:
    """Operator-visible session snapshot: used / cap / remaining / stopped / state /
    separate disposition counts (attempted·connected·answered·failed·retried·completed).
    Never raises."""
    if not sid:
        sid = await current_session_id()
    if not sid:
        cap = session_cap()
        return {
            "session_id": None,
            "active": False,
            "owner": "",
            "niche": "",
            "label": "",
            "created_at": "",
            "cap": cap,
            "used": 0,
            "remaining": cap,
            "stopped": False,
            "state": CampaignState.DRAFT.value,
            "attempted": 0,
            "connected": 0,
            "answered": 0,
            "failed": 0,
            "completed": 0,
            "retried_blocked": 0,
            "dispositions": {},
        }
    cap = session_cap()
    used = await session_attempts(sid)
    disp = await session_disposition_counts(sid)
    stopped = await session_is_stopped(sid)
    meta = await get_session_meta(sid)
    remaining = None if used < 0 else max(0, cap - used)
    if stopped:
        state = CampaignState.SESSION_STOPPED.value
    elif used >= cap:
        state = CampaignState.SESSION_LIMIT_REACHED.value
    else:
        state = CampaignState.RUNNING.value
    attempted = max(0, used) if used >= 0 else None
    connected = disp.get(VoiceDisposition.ANSWERED.value, 0)
    return {
        "session_id": sid,
        "active": not stopped and used >= 0 and used < cap,
        "owner": meta.get("owner", ""),
        "niche": meta.get("niche", ""),
        "label": meta.get("label", ""),
        "created_at": meta.get("created_at", ""),
        "cap": cap,
        "used": used,
        "remaining": remaining,
        "stopped": stopped,
        "state": state,
        "attempted": attempted,
        "connected": connected,
        "answered": connected,
        "failed": disp.get(VoiceDisposition.FAILED.value, 0),
        "completed": connected,
        "retried_blocked": await session_retried(sid),
        "dispositions": disp,
    }


# --------------------------------------------------------------------------- #
# Disposition counters (admin NUP/outcome visibility) — per IST day
# --------------------------------------------------------------------------- #
def _disp_key(disp: VoiceDisposition, kind: str) -> str:
    return f"voice_launch:disp:{kind}:{disp.value}:{_ist_date()}"


async def record_disposition(disp: Any, kind: str = "campaign") -> None:
    """Increment the per-day counter for a canonical disposition. Best-effort."""
    try:
        d = normalize_disposition(disp)
        r = await _redis()
        key = _disp_key(d, kind)
        n = int(await r.incr(key))
        if n == 1:
            try:
                await r.expire(key, _COUNTER_TTL_S)
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"[voice_launch] record_disposition skip ({e})")


async def disposition_counts_today(kind: str = "campaign") -> dict[str, int]:
    """{disposition: count} for today (IST). Missing counter => 0. Never raises."""
    out: dict[str, int] = {}
    try:
        r = await _redis()
        for d in VoiceDisposition:
            try:
                raw = await r.get(_disp_key(d, kind))
                if raw is not None and int(raw) > 0:
                    out[d.value] = int(raw)
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"[voice_launch] disposition_counts_today skip ({e})")
    return out


# --------------------------------------------------------------------------- #
# Circuit breaker (provider-failure spike / compliance-unavailable / recording)
# --------------------------------------------------------------------------- #
_CIRCUIT_KEY = "voice_launch:circuit:open"
_CONSEC_KEY = "voice_launch:consec_fail"
_CIRCUIT_TTL_S = 1800  # 30 min auto-reset


def circuit_fail_threshold() -> int:
    try:
        return max(2, int(_env("VOICE_CIRCUIT_FAIL_THRESHOLD", "5")))
    except Exception:
        return 5


async def circuit_open() -> bool:
    """True while the breaker is tripped. Never raises (unavailable => False so a
    Redis outage doesn't itself wedge the loop — the daily-cap is the fail-closed
    guard; the breaker is an availability/spike guard on top)."""
    try:
        r = await _redis()
        return bool(await r.get(_CIRCUIT_KEY))
    except Exception:
        return False


async def trip_circuit(reason: str) -> None:
    """Open the breaker (TTL auto-reset) + page ops via existing ntfy path. Idempotent-ish."""
    try:
        r = await _redis()
        already = bool(await r.get(_CIRCUIT_KEY))
        await r.set(_CIRCUIT_KEY, reason[:120], ex=_CIRCUIT_TTL_S)
        if not already:
            logger.error(f"🚨 [voice_launch] circuit breaker TRIPPED: {reason}")
            try:
                from app.platform.ops_alerts import alert_voice_circuit_breaker

                alert_voice_circuit_breaker(reason)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[voice_launch] trip_circuit noop ({e})")


async def reset_circuit() -> None:
    try:
        r = await _redis()
        await r.delete(_CIRCUIT_KEY)
        await r.delete(_CONSEC_KEY)
    except Exception:
        pass


async def record_provider_result(placed: bool, error: str = "") -> bool:
    """Update the consecutive-failure counter after a provider attempt and trip the
    breaker on a failure SPIKE. compliance_blocked (pre-dial) does NOT count as a
    provider failure. Returns True if the breaker is now open. Never raises."""
    try:
        r = await _redis()
        if placed:
            await r.delete(_CONSEC_KEY)
            return await circuit_open()
        if (error or "").strip() == "compliance_blocked":
            return await circuit_open()  # not a provider failure
        n = int(await r.incr(_CONSEC_KEY))
        if n == 1:
            try:
                await r.expire(_CONSEC_KEY, _CIRCUIT_TTL_S)
            except Exception:
                pass
        if n >= circuit_fail_threshold():
            await trip_circuit(f"provider_failure_spike ({n} consecutive; last={error[:60]})")
            return True
        return await circuit_open()
    except Exception as e:
        logger.warning(f"[voice_launch] record_provider_result noop ({e})")
        return False


# --------------------------------------------------------------------------- #
# Recording pipeline gate (block dials if MANDATORY recording path unhealthy)
# --------------------------------------------------------------------------- #
def _recordings_dir() -> Path:
    """Retention-governed recordings dir — resolved per call, never frozen at import.

    RECORDINGS_DIR keeps its current override precedence before cutover; after
    cutover the shared authority refuses an override that points anywhere but
    the canonical target. Inlined (not delegated) so the path scanner still
    binds the CREATE at ``recording_path_healthy`` to this store's legacy path.
    """
    from app.platform import runtime_data_authority as _auth

    return _auth.resolve_store_path(
        store_id="telephony.call_recordings",
        legacy_path=Path("data") / "recordings",
        target_segments=("telephony", "recordings"),
        override_env="RECORDINGS_DIR",
    )


def recording_required() -> bool:
    """Recording MANDATORY only when explicitly required (default OFF = graceful;
    existing paths that don't record are not broken). Set VOICE_RECORDING_REQUIRED=1
    for a launch that must retain call recordings (TRAI 90-day + QA)."""
    return _flag_on("VOICE_RECORDING_REQUIRED", default=False)


def recording_path_healthy() -> bool:
    """Recordings dir exists (or creatable) and is writable. Never raises."""
    try:
        d = _recordings_dir()
        d.mkdir(parents=True, exist_ok=True)
        return os.access(str(d), os.W_OK)
    except Exception:
        return False


def recording_gate_ok() -> tuple[bool, str]:
    """(ok, reason). Fail-CLOSED only when recording is REQUIRED and path unhealthy."""
    if not recording_required():
        return True, "recording_not_required"
    if recording_path_healthy():
        return True, "recording_healthy"
    return False, "recording_path_unhealthy"


# --------------------------------------------------------------------------- #
# Runtime campaign-state persistence (admin visibility) + kill toggle + status
# --------------------------------------------------------------------------- #
_STATE_KEY = "voice_launch:state"


async def set_campaign_state(state: Any) -> None:
    try:
        s = state.value if isinstance(state, CampaignState) else str(state)
        r = await _redis()
        await r.set(_STATE_KEY, s, ex=_COUNTER_TTL_S)
    except Exception:
        pass


async def get_campaign_state() -> str:
    try:
        r = await _redis()
        v = await r.get(_STATE_KEY)
        return str(v) if v else CampaignState.DRAFT.value
    except Exception:
        return CampaignState.DRAFT.value


def set_kill(on: bool) -> bool:
    """Admin global kill switch write (data-file; container-recreate ke bina flip).
    Env VOICE_LAUNCH_KILL, agar set ho, iske UPAR final rehta hai. Returns success."""
    tmp = None
    try:
        p = _kill_file()

        # Validate BEFORE any filesystem mutation: in production a checkout-local
        # or outside-root target must be refused without creating anything.
        pre = _kill_file_status()
        if pre.reason in ("INVALID_PATH", "OUTSIDE_RUNTIME_ROOT"):
            logger.warning("[voice_launch] set_kill refused (%s)", pre.reason)
            return False

        p.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"kill": bool(on)})

        # Same directory: os.replace is only atomic within one filesystem, and a
        # temp in TMPDIR can land on a different mount.
        tmp = p.with_name(p.name + ".tmp_kill")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
        tmp = None

        # Best-effort directory fsync so the rename itself survives a crash.
        # Not supported on Windows; never fatal.
        try:
            dfd = os.open(str(p.parent), os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except (AttributeError, OSError):
            pass
        return True
    except Exception as e:
        logger.warning(f"[voice_launch] set_kill failed ({e})")
        return False
    finally:
        # A surviving temp must never be mistaken for the authority.
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


async def launch_status() -> dict[str, Any]:
    """One-call admin snapshot: kill/enabled/cap/attempts/remaining/training/circuit/
    recording/state + today's disposition (NUP) counts. Never raises."""
    attempts = await attempts_today("campaign")
    cap = daily_cap("campaign")
    remaining = None if attempts < 0 else max(0, cap - attempts)
    test_attempts = await attempts_today("test")
    rec_ok, rec_reason = recording_gate_ok()
    _kill_status = admin_kill_status()
    _session = await session_status()
    return {
        "campaign_enabled": campaign_enabled(),
        # Single evaluation: the file is read once per status request, and the
        # reason travels with the flag so an operator sees WHY it is engaged
        # (MALFORMED reads very differently from FILE_ENGAGED).
        "admin_kill_engaged": _kill_status.engaged,
        "admin_kill_source": _kill_status.source,
        "admin_kill_reason": _kill_status.reason,
        "daily_cap": cap,
        "attempts_today": attempts,
        "remaining_today": remaining,
        "test_daily_cap": daily_cap("test"),
        "test_attempts_today": test_attempts,
        "concurrency_limit": concurrency_limit(),
        "training_batch_size": training_batch_size(),
        "next_training_boundary": next_training_boundary(max(0, attempts)),
        "session_cap": session_cap(),
        "session": _session,
        "circuit_open": await circuit_open(),
        "recording_required": recording_required(),
        "recording_ok": rec_ok,
        "recording_reason": rec_reason,
        "state": await get_campaign_state(),
        "dispositions_today": await disposition_counts_today("campaign"),
        "nup_today": (await disposition_counts_today("campaign")).get(
            VoiceDisposition.NUP.value, 0
        ),
    }


# --------------------------------------------------------------------------- #
# Effective campaign-state resolver (pure — no side effects)
# --------------------------------------------------------------------------- #
def resolve_campaign_state(
    *,
    configured: CampaignState | str = CampaignState.DRAFT,
    compliance_ok: bool = True,
    circuit_open: bool = False,
    training_pause: bool = False,
    attempts: int = 0,
    cap: int | None = None,
) -> CampaignState:
    """Derive the effective runtime state from the configured state + live signals.
    Precedence (safest first): admin kill > campaign disabled > compliance block >
    circuit breaker > daily limit > training pause > configured/running."""
    try:
        cfg = (
            configured if isinstance(configured, CampaignState) else CampaignState(str(configured))
        )
    except Exception:
        cfg = CampaignState.DRAFT
    cap = cap if cap is not None else daily_cap("campaign")

    if admin_kill_engaged():
        return CampaignState.PAUSED_BY_ADMIN
    if not campaign_enabled():
        return CampaignState.DRAFT
    if cfg in (CampaignState.COMPLETED, CampaignState.FAILED, CampaignState.PAUSED_BY_ADMIN):
        return cfg
    if not compliance_ok:
        return CampaignState.COMPLIANCE_BLOCKED
    if circuit_open:
        return CampaignState.PAUSED_BY_CIRCUIT_BREAKER
    if attempts >= cap:
        return CampaignState.DAILY_LIMIT_REACHED
    if training_pause:
        return CampaignState.PAUSED_FOR_TRAINING
    if cfg in _DIALABLE_STATES:
        return cfg
    if cfg == CampaignState.READY:
        return CampaignState.READY
    return cfg


__all__ = [
    "CampaignState",
    "VoiceDisposition",
    "SkipReason",
    "EligibilityResult",
    "SlotReservation",
    "state_is_dialable",
    "normalize_disposition",
    "disposition_counts_toward_cap",
    "disposition_is_connect",
    "campaign_enabled",
    "admin_kill_engaged",
    "admin_kill_status",
    "AdminKillStatus",
    "daily_cap",
    "concurrency_limit",
    "training_batch_size",
    "training_pause_due",
    "next_training_boundary",
    "session_cap",
    "new_session_id",
    "create_voice_session",
    "current_session_id",
    "get_session_meta",
    "session_attempts",
    "session_is_stopped",
    "session_stop",
    "reserve_session_slot",
    "release_session_slot",
    "record_session_disposition",
    "session_disposition_counts",
    "record_session_retry_blocked",
    "session_retried",
    "session_idem_claim",
    "session_idem_release",
    "session_status",
    "attempts_today",
    "daily_cap_reached",
    "reserve_call_slot",
    "release_call_slot",
    "record_disposition",
    "disposition_counts_today",
    "circuit_open",
    "trip_circuit",
    "reset_circuit",
    "record_provider_result",
    "circuit_fail_threshold",
    "recording_required",
    "recording_path_healthy",
    "recording_gate_ok",
    "set_campaign_state",
    "get_campaign_state",
    "set_kill",
    "launch_status",
    "is_lead_eligible_for_voice_call",
    "resolve_campaign_state",
]
