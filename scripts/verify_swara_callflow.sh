#!/usr/bin/env bash
# =============================================================================
# verify_swara_callflow.sh
# Swara (AI telecaller) call-flow verification harness  --  leadsgenai.in
#
# PURPOSE
#   One command = ek hi run me poora health snapshot + PASS/FAIL verdict, so that
#   the moment a fix lands we can prove it in minutes instead of re-deriving
#   the whole diagnosis by hand.
#
#   Bug context (2026-09-08): calls disconnect immediately on connect.
#   Observed prod signature (docker logs -t leadgen_app):
#       ... "WebSocket /api/telephony/smartflo/stream" [accepted]
#       ... [smartflo-stream] WS open niche=general client=None (...)
#       ... [smartflo-stream] WS error: (<CloseCode.NO_STATUS_RCVD: 1005>, '')
#       -> accept se drop tak ~58ms; kabhi 'connected'/'start' event aaya hi nahi.
#
# SAFETY
#   STRICTLY READ-ONLY. Koi .env edit, koi container restart, koi config change
#   NAHI karta. Sirf docker logs / docker exec printenv / fs_cli -x / cat.
#
# USAGE
#   bash scripts/verify_swara_callflow.sh                 # 60m lookback, 8s min call
#   bash scripts/verify_swara_callflow.sh 180             # 180m lookback
#   bash scripts/verify_swara_callflow.sh 60 15           # 15s min call length
#
# EXIT CODE
#   0 = sab PASS (ya sirf WARN)   1 = koi FAIL hai
# =============================================================================

set -uo pipefail

LOOKBACK_MIN="${1:-60}"
MIN_CALL_SEC="${2:-8}"
MIN_RMS="${MIN_RMS:-100}"

APP_CT="${APP_CT:-leadgen_app}"
FS_CT="${FS_CT:-leadgen-freeswitch}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
ART_DIR="${ART_DIR:-/opt/leadgen-runtime/artifacts/call_transcripts}"
PY="${PY:-python3}"

PASS=0; FAIL=0; WARN=0
FAILED=()

C_GREEN='\033[0;32m'; C_RED='\033[0;31m'; C_YEL='\033[0;33m'
C_DIM='\033[2m'; C_BOLD='\033[1m'; C_OFF='\033[0m'

ok()   { PASS=$((PASS+1)); echo -e "  ${C_GREEN}[PASS]${C_OFF} $*"; }
bad()  { FAIL=$((FAIL+1)); FAILED+=("$1"); echo -e "  ${C_RED}[FAIL]${C_OFF} $*"; }
warn() { WARN=$((WARN+1)); echo -e "  ${C_YEL}[WARN]${C_OFF} $*"; }
info() { echo -e "  ${C_DIM}[info]${C_OFF} $*"; }
head_() { echo; echo -e "${C_BOLD}$*${C_OFF}"; }

echo -e "${C_BOLD}================================================================${C_OFF}"
echo -e "${C_BOLD} Swara call-flow verification  --  $(date -u +%Y-%m-%dT%H:%M:%SZ) UTC${C_OFF}"
echo -e "${C_BOLD} lookback=${LOOKBACK_MIN}m  min_call=${MIN_CALL_SEC}s  app=${APP_CT}  fs=${FS_CT}${C_OFF}"
echo -e "${C_BOLD}================================================================${C_OFF}"

# -----------------------------------------------------------------------------
# Preflight
# -----------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "FATAL: docker not found on PATH."; exit 1
fi

# -----------------------------------------------------------------------------
# [1] App health  --  must report environment:production
# -----------------------------------------------------------------------------
head_ "[1] leadgen_app health (/health)"
HEALTH="$(curl -s --max-time 10 "$HEALTH_URL" 2>/dev/null)"
if [ -z "$HEALTH" ]; then
  bad "health endpoint unreachable at $HEALTH_URL"
else
  ENV_KIND="$(echo "$HEALTH" | "$PY" -c 'import json,sys
try:
    d=json.load(sys.stdin); print(d.get("environment","") or "")
except Exception: print("")' 2>/dev/null)"
  STATUS_KIND="$(echo "$HEALTH" | "$PY" -c 'import json,sys
try:
    d=json.load(sys.stdin); print(d.get("status","") or "")
except Exception: print("")' 2>/dev/null)"
  VERSION="$(echo "$HEALTH" | "$PY" -c 'import json,sys
try:
    d=json.load(sys.stdin); print(d.get("version","") or "")
except Exception: print("")' 2>/dev/null)"
  info "status=$STATUS_KIND  version=$VERSION  environment=$ENV_KIND"
  [ "$STATUS_KIND" = "healthy" ] && ok "health status=healthy" \
                                || bad "health status is '$STATUS_KIND' (expected healthy)"
  [ "$ENV_KIND" = "production" ] && ok "environment=production" \
                                 || bad "environment='$ENV_KIND' (expected production)"
fi

# -----------------------------------------------------------------------------
# [2] Telephony env actually visible to the app container
# -----------------------------------------------------------------------------
head_ "[2] DID / caller-ID env visible to ${APP_CT}"
CT_ENV="$(docker exec "$APP_CT" printenv 2>/dev/null)"
if [ -z "$CT_ENV" ]; then
  bad "cannot read env from container ${APP_CT} (docker exec printenv failed)"
else
  # Active path keys -> EMPTY = FAIL (call cannot be placed / gated by compliance)
  REQUIRED_ACTIVE=(
    "TELEPHONY_PROVIDER"
    "VOBIZ_CALLER_ID"
    "SMARTFLO_WS_HOST"
    "SMARTFLO_VOICE_STREAM_ENABLED"
  )
  # Informational keys -> EMPTY = WARN (provider not in use, not a blocker per se)
  OPTIONAL_KEYS=(
    "SIP_DID"
    "TATA_SMARTFLO_DID"
    "JIO_SIP_DID"
  )
  # Provider arming flags (a trunk is invisible to pick_trunk() until armed)
  ARMING_KEYS=(
    "TATA_SMARTFLO_ENABLED"
    "JIO_TRUNK_ENABLED"
  )

  get_env() { echo "$CT_ENV" | grep -m1 "^$1=" | cut -d= -f2-; }

  for k in "${REQUIRED_ACTIVE[@]}"; do
    v="$(get_env "$k")"
    if [ -n "$v" ]; then ok "$k = ${v}"
    else bad "$k is EMPTY (active outbound path key)"; fi
  done

  for k in "${OPTIONAL_KEYS[@]}"; do
    v="$(get_env "$k")"
    if [ -n "$v" ]; then ok "$k = ${v}"
    else warn "$k is EMPTY (informational - not on the active path)"; fi
  done

  for k in "${ARMING_KEYS[@]}"; do
    v="$(get_env "$k")"
    if [ -n "$v" ]; then info "$k = ${v}"
    else info "$k unset (trunk not armed -> excluded from pick_trunk())"; fi
  done

  # Consistency: active provider must have a matching caller-ID.
  PROV="$(get_env "TELEPHONY_PROVIDER")"
  case "$PROV" in
    vobiz)
      [ -n "$(get_env "VOBIZ_CALLER_ID")" ] \
        && ok "active provider '$PROV' has caller-ID VOBIZ_CALLER_ID" \
        || bad "active provider '$PROV' but VOBIZ_CALLER_ID empty -> compliance gate 'no_caller_id' blocks promo calls" ;;
    tata_smartflo)
      [ -n "$(get_env "TATA_SMARTFLO_DID")" ] \
        && ok "active provider '$PROV' has caller-ID TATA_SMARTFLO_DID" \
        || bad "active provider '$PROV' but TATA_SMARTFLO_DID empty"
      [ -n "$(get_env "TATA_SMARTFLO_ENABLED")" ] \
        || warn "provider '$PROV' but TATA_SMARTFLO_ENABLED unset -> trunk invisible to pick_trunk()" ;;
    sip)
      [ -n "$(get_env "SIP_DID")" ] \
        && ok "active provider '$PROV' has caller-ID SIP_DID" \
        || bad "active provider '$PROV' but SIP_DID empty" ;;
    *) warn "unknown/unset TELEPHONY_PROVIDER='$PROV'" ;;
  esac
fi

# -----------------------------------------------------------------------------
# [3] FreeSWITCH up?
# -----------------------------------------------------------------------------
head_ "[3] FreeSWITCH container"
FS_UP="$(docker inspect -f '{{.State.Running}}' "$FS_CT" 2>/dev/null)"
if [ "$FS_UP" = "true" ]; then
  ok "${FS_CT} is running"
else
  warn "${FS_CT} is NOT running (state='${FS_UP}') - only relevant if a SIP trunk is the active path"
fi

# -----------------------------------------------------------------------------
# [4] SIP gateway registered?
# -----------------------------------------------------------------------------
head_ "[4] SIP gateway registration (sofia)"
FS_CLI_OK=0
if [ "$FS_UP" = "true" ]; then
  if docker exec "$FS_CT" sh -lc 'command -v fs_cli >/dev/null 2>&1' 2>/dev/null; then
    FS_CLI_OK=1
  fi
fi

if [ "$FS_CLI_OK" = "1" ]; then
  SOFIA="$(docker exec "$FS_CT" fs_cli -x 'sofia status' 2>&1)"
  GW_TABLE="$(docker exec "$FS_CT" fs_cli -x 'sofia status gateway' 2>&1)"
  # keep only real gateway rows: name contains "::", and skip the header row
  GWS="$(echo "$GW_TABLE" | awk '$1 ~ /::/ && $3 != "State" && $3 != "" {print $1"|"$3}')"
  if [ -z "$GWS" ]; then
    warn "no SIP gateways configured (sofia status gateway returned none)"
  else
    ANY_REG=0
    while IFS='|' read -r gname gstate; do
      [ -z "$gname" ] && continue
      case "$gstate" in
        REGED|REG) ok "gateway ${gname} state=${gstate}"; ANY_REG=1 ;;
        NOREG)     bad "gateway ${gname} state=NOREG (SIP REGISTER not established -> calls drop on connect)" ;;
        *)         warn "gateway ${gname} state=${gstate:-unknown}" ;;
      esac
    done <<< "$GWS"
    [ "$ANY_REG" = "1" ] || info "no gateway in REGED state - see docs/SWARA_CALLFLOW_QA_20260908.md §R3"
  fi
  echo "$SOFIA" | sed 's/^/  /' | head -8
else
  if [ "$FS_UP" = "true" ]; then
    warn "fs_cli NOT available inside ${FS_CT} - cannot verify SIP registration"
    info "FALLBACK (run manually):"
    info "  docker exec -it ${FS_CT} /usr/bin/fs_cli -x 'sofia status'"
    info "  docker exec -it ${FS_CT} /usr/bin/fs_cli -x 'sofia status gateway'"
    info "  docker exec -it ${FS_CT} /usr/bin/fs_cli -x 'sofia profile external restart reloadxml'"
    info "  (or check sip_profiles/ + sip-gateways/ XML, then 'reloadxml')"
  else
    warn "skipped - ${FS_CT} not running"
  fi
fi

# -----------------------------------------------------------------------------
# [5] Stream logs in the lookback window
# -----------------------------------------------------------------------------
head_ "[5] [smartflo-stream] / [vobiz log lines (last ${LOOKBACK_MIN}m)"
APP_LOGS="$(docker logs --since "${LOOKBACK_MIN}m" "$APP_CT" 2>&1)"
if [ -z "$APP_LOGS" ]; then
  warn "no container logs returned for ${APP_CT} in the last ${LOOKBACK_MIN}m"
else
  MARKERS="$(echo "$APP_LOGS" | grep -aoE '\[(smartflo-stream|vobiz[a-z_-]*)\][^"\\]{0,140}' | sort | uniq -c | sort -rn | head -25)"
  if [ -n "$MARKERS" ]; then
    echo "$MARKERS" | sed 's/^/  /'
  else
    warn "zero [smartflo-stream]/[vobiz...] log lines in the last ${LOOKBACK_MIN}m"
  fi

  WS_ACCEPT="$(echo "$APP_LOGS" | grep -ac 'WebSocket /api/telephony/smartflo/stream' )"
  WS_OPEN="$(echo "$APP_LOGS" | grep -ac 'WS open')"
  CONNECTED_EV="$(echo "$APP_LOGS" | grep -ac 'connected event')"
  START_EV="$(echo "$APP_LOGS" | grep -ac 'start streamSid')"
  info "WS accepted=${WS_ACCEPT}  WS open=${WS_OPEN}  'connected' events=${CONNECTED_EV}  'start' events=${START_EV}"

  if [ "$WS_ACCEPT" -gt 0 ] && [ "$CONNECTED_EV" -eq 0 ] && [ "$START_EV" -eq 0 ]; then
    bad "WS connections accepted but NO 'connected'/'start' event ever arrived -> provider drops on handshake (1005 signature)"
  elif [ "$WS_ACCEPT" -gt 0 ]; then
    ok "stream handshake events observed (connected/start)"
  else
    warn "no inbound stream connection in the window - cannot judge handshake"
  fi
fi

# -----------------------------------------------------------------------------
# [6] Drops: 1005 / WS error
# -----------------------------------------------------------------------------
head_ "[6] Drop signature (1005 / WS error)"
if [ -n "${APP_LOGS:-}" ]; then
  DROP_1005="$(echo "$APP_LOGS" | grep -ac '1005' )"
  DROP_WSERR="$(echo "$APP_LOGS" | grep -ac 'WS error')"
  info "lines containing 1005 = ${DROP_1005}; 'WS error' lines = ${DROP_WSERR}"
  if [ "$DROP_1005" -eq 0 ] && [ "$DROP_WSERR" -eq 0 ]; then
    ok "no 1005 / WS-error lines in the last ${LOOKBACK_MIN}m"
  else
    bad "${DROP_WSERR} WS-error / ${DROP_1005} 1005 lines in the last ${LOOKBACK_MIN}m"
    echo "$APP_LOGS" | grep -aE '1005|WS error' | grep -aoE '.{0,120}(1005|WS error).{0,60}' | tail -5 | sed 's/^/  /'
  fi
else
  warn "skipped (no logs)"
fi

# -----------------------------------------------------------------------------
# [7] Call artifacts: duration / media_frames / caller_rms_max
# -----------------------------------------------------------------------------
head_ "[7] Call artifacts (${ART_DIR})"

# NOTE: the two python steps below are written to temp files on purpose --
# inlining them via `python3 -c '...'` made nested quote escaping explode on
# some hosts. Temp files keep the script portable bash.
QA_TMP="$(mktemp -d 2>/dev/null || echo /tmp/_swara_qa_$$)"
mkdir -p "$QA_TMP"

cat > "$QA_TMP/scan.py" <<'PYEOF'
import json, os, glob, datetime

art_dir = os.environ["ART_DIR"]
lookback = int(os.environ.get("LOOKBACK_MIN", "60"))
min_call = float(os.environ.get("MIN_CALL_SEC", "8"))
min_rms = float(os.environ.get("MIN_RMS", "100"))
now = datetime.datetime.now(datetime.timezone.utc)
cut = now - datetime.timedelta(minutes=lookback)


def parse(ts):
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts)
    except Exception:
        return None


rows = []
for p in sorted(glob.glob(os.path.join(art_dir, "*.json"))):
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        continue
    st = parse(d.get("started_at"))
    en = parse(d.get("ended_at"))
    dur = round((en - st).total_seconds(), 2) if (st and en) else None
    rows.append({
        "file": os.path.basename(p),
        "provider": d.get("provider"),
        "stream_sid": d.get("stream_sid"),
        "from": d.get("from"),
        "to": d.get("to"),
        "started_at": d.get("started_at") or "",
        "duration_s": dur,
        "media_frames": d.get("media_frames"),
        "caller_rms_max": d.get("caller_rms_max"),
        "messages": len(d.get("messages") or []),
        "fresh": bool(st and st >= cut),
        "probe": str(d.get("stream_sid") or "").startswith("probe-"),
    })

rows.sort(key=lambda r: r["started_at"], reverse=True)
print(json.dumps({
    "dir": art_dir,
    "total": len(rows),
    "newest": rows[:5],
    "fresh": [r for r in rows if r["fresh"]],
    "min_call_sec": min_call,
    "min_rms": min_rms,
}, indent=1))
PYEOF

cat > "$QA_TMP/report.py" <<'PYEOF'
import json, sys

d = json.load(sys.stdin)
print("  dir=%s  total_artifacts=%s  fresh(in window)=%s"
      % (d["dir"], d["total"], len(d["fresh"])))
for r in d["newest"]:
    tag = "  <-- PROBE (synthetic)" if r["probe"] else ""
    print("   - %s" % r["file"])
    print("     provider=%s stream_sid=%s from=%s to=%s"
          % (r["provider"], r["stream_sid"], r["from"], r["to"]))
    print("     duration_s=%s media_frames=%s caller_rms_max=%s messages=%s%s"
          % (r["duration_s"], r["media_frames"], r["caller_rms_max"],
             r["messages"], tag))
PYEOF

cat > "$QA_TMP/verdict.py" <<'PYEOF'
import json, sys

d = json.load(sys.stdin)
real = [r for r in d["fresh"] if not r["probe"]]
if not real:
    print("NO_REAL_ARTIFACT")
    raise SystemExit
r = real[0]
dur = r["duration_s"] or 0.0
mf = r["media_frames"] or 0
rms = r["caller_rms_max"] or 0
bad = []
if dur < d["min_call_sec"]:
    bad.append("duration %ss < %ss" % (dur, d["min_call_sec"]))
if mf <= 0:
    bad.append("media_frames=0")
if rms < d["min_rms"]:
    bad.append("caller_rms_max %s < %s" % (rms, d["min_rms"]))
if r["messages"] < 2:
    bad.append("messages=%s (<2, no conversation)" % r["messages"])
print("OK" if not bad else "BAD:" + ", ".join(bad))
PYEOF

ART_JSON="$(ART_DIR="$ART_DIR" LOOKBACK_MIN="$LOOKBACK_MIN" \
            MIN_CALL_SEC="$MIN_CALL_SEC" MIN_RMS="$MIN_RMS" \
            "$PY" "$QA_TMP/scan.py" 2>"$QA_TMP/scan.err")"
if [ -z "$ART_JSON" ]; then
  warn "could not parse artifacts from ${ART_DIR}"
  [ -s "$QA_TMP/scan.err" ] && sed 's/^/  /' "$QA_TMP/scan.err" | head -5
else
  echo "$ART_JSON" | "$PY" "$QA_TMP/report.py"

  VERDICT="$(echo "$ART_JSON" | "$PY" "$QA_TMP/verdict.py")"
  case "$VERDICT" in
    OK)   ok "freshest real call artifact is sane (duration/media_frames/caller_rms_max)" ;;
    NO_REAL_ARTIFACT)
          if echo "$ART_JSON" | grep -q '"probe": true'; then
            warn "no REAL call artifact in the last ${LOOKBACK_MIN}m (only synthetic probe artifacts) - cannot prove a live call yet"
          else
            warn "no call artifact in the last ${LOOKBACK_MIN}m"
          fi ;;
    BAD:*) bad "freshest real call artifact unhealthy -> ${VERDICT#BAD:}" ;;
    *)     warn "artifact verdict unparseable: ${VERDICT}" ;;
  esac
fi
rm -rf "$QA_TMP" 2>/dev/null || true

# -----------------------------------------------------------------------------
# [8] Global outbound kill switch (VOICE_LAUNCH_KILL)
# -----------------------------------------------------------------------------
# Semantics source-verified against app/telephony/voice_launch.py
# (admin_kill_status(), 2026-09-08):
#   0 / false / no / off -> DISENGAGED = outbound calls ARE allowed.
#                           This is the NORMAL production state.
#   1 / true / yes / on  -> ENGAGED = ALL outbound calls are blocked.
#                           Expected only while a deploy has flipped it on.
#   unset / unrecognised -> the runtime is FAIL-CLOSED (it engages the kill
#                           switch), so no outbound call can be placed.
#
# NOTE: this is NOT the same as the ARMING_KEYS trunk flags in section [2]
# (TATA_SMARTFLO_ENABLED / JIO_TRUNK_ENABLED) -- those only decide whether a
# trunk is visible to pick_trunk(). "Kill switch engaged" and "trunk not armed"
# are two different things; do not read one as the other.
head_ "[8] Global outbound kill switch (VOICE_LAUNCH_KILL)"
KILL_RAW="$(docker exec "$APP_CT" printenv VOICE_LAUNCH_KILL 2>/dev/null)"
KILL_V="$(printf '%s' "${KILL_RAW:-}" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"
case "$KILL_V" in
  0|false|no|off)
    ok "VOICE_LAUNCH_KILL='${KILL_V}' -> kill switch DISENGAGED, outbound calls allowed (normal production state)" ;;
  1|true|yes|on)
    warn "VOICE_LAUNCH_KILL='${KILL_V}' -> kill switch ENGAGED, ALL outbound calls blocked (expected only while a deploy flips it on)" ;;
  "")
    bad "VOICE_LAUNCH_KILL is UNSET in ${APP_CT} -> fail-closed: runtime engages the kill switch, no outbound calls" ;;
  *)
    bad "VOICE_LAUNCH_KILL='${KILL_V}' is not a recognised token -> fail-closed: runtime engages the kill switch" ;;
esac

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo
echo -e "${C_BOLD}================================================================${C_OFF}"
if [ "$FAIL" -eq 0 ] && [ "$WARN" -eq 0 ]; then
  echo -e "${C_BOLD} VERDICT: ${C_GREEN}ALL PASS${C_OFF}  (pass=${PASS} fail=0 warn=0)"
elif [ "$FAIL" -eq 0 ]; then
  echo -e "${C_BOLD} VERDICT: ${C_YEL}PASS WITH WARNINGS${C_OFF}  (pass=${PASS} fail=0 warn=${WARN})"
else
  echo -e "${C_BOLD} VERDICT: ${C_RED}FAIL${C_OFF}  (pass=${PASS} fail=${FAIL} warn=${WARN})"
  for f in "${FAILED[@]}"; do echo -e "   ${C_RED}- ${f}${C_OFF}"; done
fi
echo -e "${C_BOLD}================================================================${C_OFF}"
echo -e "${C_DIM} READ-ONLY run - no config was changed. Detailed QA rubric:${C_OFF}"
echo -e "${C_DIM}   docs/SWARA_CALLFLOW_QA_20260908.md${C_OFF}"

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
