"""Regression guard for the check_secrets.py MTProto `api_hash` blind spot.

2026-09-22: a LIVE Telegram MTProto `api_id`/`api_hash` pair sat on PUBLIC `main`
in 8 places across 6 files — 4 scripts as `os.environ.get(...)` source defaults and
2 runbooks as printed literals. `scripts/check_secrets.py` MISSED every one of them.

Root cause (two independent gaps, both verified by direct pattern probe):

1. **Label vocabulary.** Both the env-fallback pattern and the unquoted-label
   pattern enumerated `api_key|apikey|secret|token|passwd|password|...`. The word
   **`api_hash`** was not in either list. The regex anchors on the LABEL before the
   `=` — i.e. on `API_HASH` — never on the looked-up var name `TELEGRAM_API_HASH`
   that appears after it. Proven: the `API_HASH`/`API_ID` shapes were MISSED while
   the `SECRET_KEY` / `API_KEY` controls were DETECTED.

2. **Word-boundary anchoring (found while fixing #1).** The unquoted-label pattern
   opened with a bare `\\b(?:...)`, but a label is very often a SUFFIX of a longer
   underscore-joined identifier. In `TELEGRAM_API_HASH` there is no word boundary
   before `API` — both `_` and `A` are word characters — so `export
   TELEGRAM_API_HASH=<32-hex>` could never match. Fixed to `\\b\\w*(?:...)\\w*`,
   mirroring the env-fallback pattern's shape.

MTProto credentials are a distinct secret CLASS (api_id + api_hash + session_string)
and are exactly what this project's Telegram tooling uses, so the hole was a
recurrence risk rather than a one-off.

These tests pin BOTH directions so the hole cannot silently reopen:
  1. every shape that actually leaked MUST be caught, and
  2. the scrubbed replacements MUST NOT be flagged — a scanner that cries wolf on
     `$TELEGRAM_API_HASH` gets muted, and a muted scanner is how the hole survived.

The literal values below are OBVIOUSLY-SYNTHETIC dummies, never real credentials.
They deliberately avoid every cs.PLACEHOLDER substring (`example`, `dummy`,
`changeme`, `abcdef`, `1234567890`, ...) — a placeholder value is *correctly*
suppressed, which would make the assertion test the wrong thing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "check_secrets_mtproto_under_test", ROOT / "scripts" / "check_secrets.py"
)
assert _SPEC and _SPEC.loader
cs = importlib.util.module_from_spec(_SPEC)
sys.modules["check_secrets_mtproto_under_test"] = cs
_SPEC.loader.exec_module(cs)

# Synthetic, high-entropy, contains both letters and digits, and free of every
# PLACEHOLDER substring. NOT a real credential.
H = "7c9e1f4a2b8d6053ea47c19b3f82d501"


def _flagging_patterns(line: str) -> list[str]:
    """Mirror scan_file's decision across ALL patterns."""
    if "nosecret" in line or cs.PLACEHOLDER.search(line):
        return []
    hits = []
    for label, pat in cs.PATTERNS:
        m = pat.search(line)
        if not m:
            continue
        if label.startswith("env-lookup fallback literal") and m.groups():
            if cs.FALLBACK_ALLOW.match((m.group(1) or "").strip()):
                continue
        hits.append(label)
    return hits


# ---------------------------------------------------------------- must CATCH
#
# Every line below carries a `nosecret` marker: this suite deliberately contains
# the leak SHAPE, so check_secrets.py must skip these lines or it self-triggers
# and turns CI red. The marker is the scanner's documented escape hatch.

LEAKS = {
    # --- gap 1: label vocabulary, script env-fallback form ------------------
    "script API_HASH env-fallback": (
        f'API_HASH = os.environ.get("TELEGRAM_API_HASH", "{H}")'  # nosecret
    ),
    "script SESSION_STRING env-fallback": (
        f'SESSION_STRING = os.getenv("SESSION_STRING", "{H}")'  # nosecret
    ),
    "script AUTH_HASH env-fallback": (
        f'AUTH_HASH = os.environ.get("TELEGRAM_AUTH_HASH", "{H}")'  # nosecret
    ),
    # --- gap 2: word-boundary anchoring, doc forms --------------------------
    "doc export TELEGRAM_API_HASH": (
        f"export TELEGRAM_API_HASH={H}"  # nosecret
    ),
    "doc inline api_hash=<hex>": (
        f"**Credentials:** api_id=30160587, api_hash={H}"  # nosecret
    ),
    "doc --api-hash flag": (
        f'  --api-hash "{H}" \\'  # nosecret
    ),
    "doc bare api-hash": (
        f"api-hash: {H}"  # nosecret
    ),
    # --- gap 2, second class found in the same incident --------------------
    # `TELEGRAM_WEBHOOK_SECRET=<48-hex>` sat on PUBLIC main in
    # docs/TELEGRAM_ENTERPRISE_SETUP_COMPLETE.md, undetected for the SAME reason:
    # there is no word boundary before `SECRET` inside `..._WEBHOOK_SECRET`.
    "doc TELEGRAM_WEBHOOK_SECRET": (
        f"- **Secret**: TELEGRAM_WEBHOOK_SECRET={H}"  # nosecret
    ),
    "doc webhook_secret label": (
        f"webhook_secret = {H}"  # nosecret
    ),
}


@pytest.mark.parametrize("name", sorted(LEAKS))
def test_mtproto_leak_shape_is_flagged(name: str) -> None:
    line = LEAKS[name]
    hits = _flagging_patterns(line)
    assert hits, (
        f"REGRESSION: {name} not flagged. The MTProto api_hash blind spot is back — "
        f"a live Telegram credential in this shape would ship to a PUBLIC repo "
        f"undetected, which is exactly what happened on 2026-09-22.\n  line: {line}"
    )


def test_label_is_matched_when_it_is_a_suffix_of_a_longer_identifier() -> None:
    """Pins gap 2 directly: `TELEGRAM_API_HASH` has NO word boundary before `API`.

    `_` and `A` are both word characters, so a bare `\\b(?:...)` anchor can never
    match here. This is the assertion that fails if the anchor regresses.
    """
    line = f"export TELEGRAM_API_HASH={H}"  # nosecret
    assert _flagging_patterns(line), (
        "REGRESSION: a label that is a SUFFIX of a longer underscore-joined "
        "identifier is no longer matched. Restore the `\\b\\w*(?:...)\\w*` anchor."
    )


def test_api_hash_is_in_the_env_fallback_label_vocabulary() -> None:
    """The vocabulary itself — the most direct guard against a silent revert."""
    pat = None
    for label, p in cs.PATTERNS:
        if label == "env-lookup fallback literal (getenv/os.environ.get default)":
            pat = p
            break
    assert pat is not None, "env-fallback pattern missing from PATTERNS"
    for label_word in ("API_HASH", "APIHASH", "SESSION_STRING", "AUTH_HASH"):
        probe = f'{label_word} = os.getenv("{label_word}", "{H}")'  # nosecret
        assert pat.search(probe), (
            f"REGRESSION: `{label_word}` dropped out of the env-fallback label "
            f"vocabulary; a live default in this shape would go undetected."
        )


_SUFFIX_LABEL = "Telegram suffix-label credential (api_hash / session_string / webhook_secret)"


def test_suffix_label_pattern_exists() -> None:
    """The dedicated suffix-label pattern must exist.

    This is the design decision that made the fix shippable: the generic patterns
    stay untouched (so their tuned false-positive profile is preserved) and the
    suffix-label classes get their own narrowly-scoped pattern.
    """
    labels = [label for label, _ in cs.PATTERNS]
    assert _SUFFIX_LABEL in labels, (
        f"REGRESSION: pattern {_SUFFIX_LABEL!r} missing from PATTERNS. Without it the "
        f'doc forms (`export TELEGRAM_API_HASH=`, `--api-hash "`, `webhook_secret =`) '
        f"go undetected — which is exactly what happened on 2026-09-22."
    )


# Noise shapes that a NAIVE widening of the generic patterns produced. The first
# attempt added `\b\w*` to the generic "unquoted credential" alternation and this
# created 225 repo-wide findings, ~220 of them false positives. These cases pin the
# reason the dedicated-pattern design was chosen: a noisy scanner gets muted.
#
# The `# nosecret` markers are REQUIRED, not cosmetic. Once ruff collapsed these
# entries onto single lines, the GENERIC patterns legitimately match them — e.g.
# `token` label followed by a 43-char identifier run. That the generic patterns
# match this noise is precisely the point of the test, and precisely why the
# suffix-label pattern must stay narrow. The marker is check_secrets.py's documented
# escape hatch for deliberate false positives. Put it on the VALUE line: that is the
# line the scanner reads.

NOISE = {
    "secrets baseline sha1": (
        '    "hashed_secret": "b60d121b438a380c343d5ec3c2037564b82ffef3",'  # nosecret
    ),
    "test fn name with password": (
        "def test_change_password_returns_409_when_no_credential_row(client, monkeypatch):"  # nosecret
    ),
    "test fn name with token": (
        "def test_token_store_unavailable_fails_closed_503(monkeypatch):"  # nosecret
    ),
    "test env token literal": (
        '    monkeypatch.setenv("FASTAPI_MCP_TOKEN", "test-token-32-chars-or-longer-aaa")'  # nosecret
    ),
}


@pytest.mark.parametrize("name", sorted(NOISE))
def test_suffix_label_pattern_does_not_flag_noise(name: str) -> None:
    line = NOISE[name]
    pat = None
    for label, p in cs.PATTERNS:
        if label == _SUFFIX_LABEL:
            pat = p
            break
    assert pat is not None, f"pattern {_SUFFIX_LABEL!r} missing"
    assert not pat.search(line), (
        f"FALSE POSITIVE: {name} matched the suffix-label pattern. Widening this "
        f"pattern toward the generic `secret|token|password` vocabulary is what "
        f"produced 225 repo-wide findings; keep the keyword set narrow.\n  line: {line}"
    )


# ------------------------------------------------------------ must NOT flag

CLEAN = {
    # The actual scrubbed replacements shipped in the fix — these MUST stay quiet.
    "scrubbed empty default": 'API_HASH = os.environ.get("TELEGRAM_API_HASH", "").strip()',
    "scrubbed $VAR in flag": '  --api-hash "$TELEGRAM_API_HASH" \\',
    "scrubbed export $VAR": "export TELEGRAM_API_HASH=$TELEGRAM_API_HASH",
    "scrubbed prose mention": (
        "Supplied via the `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` environment variables."
    ),
    "scrubbed rotate note": ("The api_hash must be rotated at my.telegram.org before merging."),
    "scrubbed short var ref": 'echo "TELEGRAM_API_HASH is required"',
    # Placeholder forms are the documented way to write a runbook safely.
    "placeholder <your_api_hash>": "export TELEGRAM_API_HASH=<your_api_hash>",
    "placeholder changeme": f'API_HASH = os.environ.get("TELEGRAM_API_HASH", "changeme-{H}")',
}


@pytest.mark.parametrize("name", sorted(CLEAN))
def test_scrubbed_and_placeholder_forms_are_not_flagged(name: str) -> None:
    line = CLEAN[name]
    hits = _flagging_patterns(line)
    assert not hits, (
        f"FALSE POSITIVE: {name} flagged by {hits}. A scanner that cries wolf on the "
        f"SCRUBBED form gets muted, and a muted scanner is how this hole survived.\n"
        f"  line: {line}"
    )


def test_numeric_api_id_alone_is_not_treated_as_a_secret() -> None:
    """Documented design decision, pinned so it is not 'fixed' by accident.

    An `api_id` is a semi-public numeric identifier; only the `api_hash` (and a
    `session_string`) are secrets. The env-fallback pattern requires a >=20-char
    literal, so an 8-digit api_id default can never match. Lowering that threshold
    to catch api_id would flood the scanner with false positives — which is the
    failure mode this whole suite exists to prevent.
    """
    line = 'API_ID = os.environ.get("TELEGRAM_API_ID", "30160587")'
    assert not _flagging_patterns(line)


# ------------------------------------------------ Telegram bot-token shape
#
# Second pass, 2026-09-22. The suffix-label pattern keys off the LABEL, so it only
# fires when the author names the thing. A bot token is self-identifying by SHAPE
# (`<8-12 digits>:AA<33+ base64url>`), so it must be caught wherever it lands and
# under ANY variable name — including one a future author invents. All three live
# tokens in this repo gate the owner control plane, which is why the class is worth
# catching by shape rather than by name.
#
# The synthetic token is BUILT by concatenation, never written as one literal. A
# literal would make this suite flag ITSELF, and marking the must-CATCH lines with
# `# nosecret` would make `_flagging_patterns` return early — so the assertion
# would pass while testing nothing. Building it keeps both directions honest.

_BOT_LABEL = "Telegram bot-token shape (digits + colon-AA + base64url)"
_BOT_TOKEN = "8123456789:AA" + "Hk7Qm2Xp9Rt4Vb6Nz1Ld8Wy3Cs5Fg0Ju2"


def _bot_pattern():
    for label, pat in cs.PATTERNS:
        if label == _BOT_LABEL:
            return pat
    return None


def test_bot_token_pattern_exists() -> None:
    assert _bot_pattern() is not None, (
        f"pattern {_BOT_LABEL!r} is missing — the bot-token class is uncovered again. "
        f"If it was renamed, update _BOT_LABEL; do not silently drop the coverage."
    )


def test_synthetic_bot_token_fixture_has_the_real_shape() -> None:
    """Guard the fixture itself: if the tail is too short, every must-CATCH case
    below would pass vacuously by asserting on a string that is not a token."""
    tail = _BOT_TOKEN.split(":AA", 1)[1]
    assert len(tail) >= 33, f"fixture tail is only {len(tail)} chars; the real shape needs 33+"
    assert _bot_pattern().search(_BOT_TOKEN), (
        "fixture does not match the pattern it is meant to test"
    )


BOT_TOKEN_LEAKS = {
    "bare in runbook prose": f"Authenticate with {_BOT_TOKEN} before deploying.",
    "env assignment": f"TELEGRAM_BOT_TOKEN={_BOT_TOKEN}",
    "shell export": f"export TELEGRAM_JARVIS_BOT_TOKEN={_BOT_TOKEN}",
    "yaml value": f'  token: "{_BOT_TOKEN}"',
    "json value": f'  "notify_token": "{_BOT_TOKEN}",',
    "unknown future variable name": f"OWNER_RELAY_CREDENTIAL={_BOT_TOKEN}",
}


@pytest.mark.parametrize("name", sorted(BOT_TOKEN_LEAKS))
def test_bot_token_shape_is_flagged_regardless_of_label(name: str) -> None:
    pat = _bot_pattern()
    assert pat is not None
    line = BOT_TOKEN_LEAKS[name]
    assert pat.search(line), (
        f"REGRESSION: {name} not flagged. A bot token is identified by SHAPE and must "
        f"be caught under ANY variable name — that is the entire point of this pattern. "
        f"If this fails, the scanner has been narrowed back to label-matching.\n"
        f"  line: {line}"
    )


BOT_TOKEN_CLEAN = {
    # Scrubbed / reference forms — must stay quiet or the scanner gets muted.
    "shell var reference": "export TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}",
    "bare env lookup": 'TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]',
    "prose placeholder": "Set TELEGRAM_BOT_TOKEN=your-bot-token-here",
    "angle placeholder": "TELEGRAM_BOT_TOKEN=<token>",
    "empty default": 'BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "")',
    # High-entropy but NOT token-shaped: this is what keeps the pattern precise.
    "hex digest": f"sha256={H}",
    "uuid": "550e8400-e29b-41d4-a716-446655440000",
    "git sha": "commit bbf8b5e6c1a94f2d8e7b03a5c6d1e4f7082a9b3c",
    "iso timestamp": "2026-09-22T17:43:17.026895800+05:30",
    "AA infix but short tail": "8123456789:AAHk7Qm2Xp",
    "digits colon AA then space": f"ratio {H[:8]}:AA is not a token",
    "too few leading digits": "1234567:AAHk7Qm2Xp9Rt4Vb6Nz1Ld8Wy3Cs5Fg0Ju2",
}


@pytest.mark.parametrize("name", sorted(BOT_TOKEN_CLEAN))
def test_bot_token_shape_does_not_flag_noise(name: str) -> None:
    pat = _bot_pattern()
    assert pat is not None
    line = BOT_TOKEN_CLEAN[name]
    assert not pat.search(line), (
        f"FALSE POSITIVE: {name} matched the bot-token shape pattern. This pattern was "
        f"shipped only because a repo-wide measurement found 0 matches across all 5,087 "
        f"tracked files. Widening it past the real token shape reintroduces the noise "
        f"that gets a scanner muted.\n  line: {line}"
    )
