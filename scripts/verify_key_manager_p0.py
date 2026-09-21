"""Standalone P0 verification for app/platform/key_manager.py (2026-09-21).

Runs the router on a minimal FastAPI app (no full app.main boot) so the core
hardening can be proven locally without the full 272-package dependency tree.
CI (required checks pytest + ruff + secret-scanning) is the authoritative
gate for full-suite integration.

Checks:
  1. 401 fail-closed when ADMIN_API_KEY is unset
  2. 401 on wrong X-API-Key
  3. 200 + encrypted-at-rest write with valid Fernet KEYS_MASTER_KEY
  4. 503 fail-closed when KEYS_MASTER_KEY missing (no plaintext write)
  5. Redacted response leaks no key fragment
  6. Legacy plaintext entry flagged rotation_required
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

# Ensure the project root (containing `app/`) is importable when run as a script.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("RUN_IN_PROCESS_SCHEDULER", "0")
os.environ.setdefault("TEAM_AUTOMATION", "0")

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, bool, str]] = []


def check(name: str, fn):
    try:
        fn()
        results.append((PASS, name, ""))
    except Exception as e:
        results.append((FAIL, name, f"{type(e).__name__}: {e}"))
        traceback.print_exc()


def main() -> int:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.platform.key_manager as km_mod

    workdir = tempfile.mkdtemp(prefix="km_p0_")
    km_mod.KEYS_FILE = Path(workdir) / "keys.json"
    km_mod.AUDIT_LOG = Path(workdir) / "audit.log"

    app = FastAPI()
    app.include_router(km_mod.router)
    client = TestClient(app)

    keys_file = os.path.join(workdir, "keys.json")

    # ── 1. No ADMIN_API_KEY -> 401 fail-closed on every route
    for k in ("ADMIN_API_KEY", "KEYS_MASTER_KEY"):
        os.environ.pop(k, None)

    def c1():
        r = client.post("/api/admin/keys/set", json={"service": "ts_a", "key": "k12345678"})
        assert r.status_code == 401, f"set without key: {r.status_code}"
        r = client.get("/api/admin/keys/audit")
        assert r.status_code == 401, f"audit without key: {r.status_code}"

    check("1. 401 fail-closed when ADMIN_API_KEY unset", c1)

    # ── 2. Wrong key -> 401
    os.environ["ADMIN_API_KEY"] = "owner-key-123"

    def c2():
        r = client.get("/api/admin/keys/audit", headers={"X-API-Key": "attacker"})
        assert r.status_code == 401, f"wrong key: {r.status_code}"

    check("2. 401 on wrong X-API-Key", c2)

    # ── 3. No master key -> 503, and keys.json never gets plaintext
    os.environ.pop("KEYS_MASTER_KEY", None)
    if os.path.exists(keys_file):
        os.remove(keys_file)

    def c3():
        r = client.post(
            "/api/admin/keys/set",
            json={"service": "ts_a", "key": "tsk_live_secret_12345678"},
            headers={"X-API-Key": "owner-key-123"},
        )
        assert r.status_code == 503, f"expected 503 fail-closed, got {r.status_code}"
        if os.path.exists(keys_file):
            assert "tsk_live_secret_12345678" not in open(keys_file).read(), "plaintext leaked"

    check("3. 503 fail-closed + no plaintext when KEYS_MASTER_KEY absent", c3)

    # ── 4. Valid master key -> encrypted write
    from cryptography.fernet import Fernet

    os.environ["KEYS_MASTER_KEY"] = Fernet.generate_key().decode()
    raw = "tsk_live_secret_99988877"

    def c4():
        r = client.post(
            "/api/admin/keys/set",
            json={"service": "ts_a", "key": raw},
            headers={"X-API-Key": "owner-key-123"},
        )
        assert r.status_code == 200, r.text
        stored = json.loads(open(keys_file).read())
        val = stored["ts_a"]["value"]
        assert raw not in val, "raw key in store"
        assert val.startswith("fm1:")

    check("4. Encrypted at rest with Fernet master key", c4)

    # ── 5. Redacted endpoint leaks nothing
    def c5():
        r = client.get("/api/admin/keys/redacted/ts_a", headers={"X-API-Key": "owner-key-123"})
        assert r.status_code == 200
        body = r.json()
        assert body["storage"] == "encrypted" and body["rotation_required"] is False
        for frag in (raw, raw[:8], raw[-4:]):
            assert frag not in r.text, f"leak {frag!r}"

    check("5. Redacted owner-visible state, no key fragments", c5)

    # ── 6. Legacy plaintext flagged
    legacy = os.path.join(workdir, "legacy_keys.json")
    json.dump({"ts_b": {"value": "old_plaintext_key_abcdef"}}, open(legacy, "w"))
    km_mod.KEYS_FILE = Path(legacy)
    km_mod._key_manager = None

    def c6():
        r = client.get("/api/admin/keys/redacted/ts_b", headers={"X-API-Key": "owner-key-123"})
        assert r.status_code == 200
        assert r.json()["rotation_required"] is True

    check("6. Legacy plaintext entry -> rotation_required", c6)

    # ── 7. Rotate also fails closed without a master key
    km_mod.KEYS_FILE = Path(workdir) / "keys.json"
    km_mod._key_manager = None
    os.environ.pop("KEYS_MASTER_KEY", None)
    json.dump({"ts_a": {"value": "fm1:seeded"}}, open(keys_file, "w"))

    def c7():
        r = client.post(
            "/api/admin/keys/rotate",
            json={"service": "ts_a", "new_key": "tsk_rotated_12345678"},
            headers={"X-API-Key": "owner-key-123"},
        )
        assert r.status_code == 503, f"rotate must fail closed, got {r.status_code}"

    check("7. /rotate fails closed (503) without KEYS_MASTER_KEY", c7)

    # ── 8. Malformed master key must not degrade to plaintext
    os.environ["KEYS_MASTER_KEY"] = "not-a-valid-fernet-key"

    def c8():
        r = client.post(
            "/api/admin/keys/set",
            json={"service": "ts_a", "key": "tsk_live_invalidmaster_1"},
            headers={"X-API-Key": "owner-key-123"},
        )
        assert r.status_code == 503, f"expected 503, got {r.status_code}"
        assert "tsk_live_invalidmaster_1" not in open(keys_file).read()

    check("8. Invalid KEYS_MASTER_KEY -> 503, no plaintext", c8)

    # ── 9+10. Clean error codes instead of opaque 500s
    os.environ["KEYS_MASTER_KEY"] = Fernet.generate_key().decode()

    def c9():
        r = client.post(
            "/api/admin/keys/set",
            json={"service": "ts_a", "key": "short"},
            headers={"X-API-Key": "owner-key-123"},
        )
        assert r.status_code == 400, f"short key should be 400, got {r.status_code}"

    check("9. Short key -> 400 (not 500)", c9)

    def c10():
        r = client.post(
            "/api/admin/keys/rotate",
            json={"service": "no_such_service", "new_key": "tsk_rotated_12345678"},
            headers={"X-API-Key": "owner-key-123"},
        )
        assert r.status_code == 404, f"unknown service should be 404, got {r.status_code}"

    check("10. Unknown service rotate -> 404 (not 500)", c10)

    # ── 11. Audit trail carries no key fragments
    audit_file = os.path.join(workdir, "audit.log")
    raw11 = "tsk_audit_probe_555666777888"

    def c11():
        if os.path.exists(audit_file):
            os.remove(audit_file)
        r = client.post(
            "/api/admin/keys/set",
            json={"service": "ts_a", "key": raw11},
            headers={"X-API-Key": "owner-key-123"},
        )
        assert r.status_code == 200, r.text
        text = open(audit_file).read()
        for frag in (raw11, raw11[:8], raw11[-4:]):
            assert frag not in text, f"key fragment {frag!r} leaked into audit log"

    check("11. Audit log contains no key material", c11)

    # ── 12. Rotating a legacy plaintext entry migrates it to ciphertext
    def c12():
        legacy_path = os.path.join(workdir, "legacy_rotate.json")
        json.dump({"ts_c": {"value": "old_plaintext_value_abc"}}, open(legacy_path, "w"))
        km_mod.KEYS_FILE = Path(legacy_path)
        km_mod._key_manager = None
        master = os.environ["KEYS_MASTER_KEY"]
        r = client.post(
            "/api/admin/keys/rotate",
            json={"service": "ts_c", "new_key": "tsk_new_encrypted_value_99"},
            headers={"X-API-Key": "owner-key-123"},
        )
        assert r.status_code == 200, r.text
        stored = json.loads(open(legacy_path).read())["ts_c"]["value"]
        assert stored.startswith("fm1:"), "legacy entry not migrated to ciphertext"
        assert Fernet(master.encode()).decrypt(stored[len("fm1:") :]).decode() == (
            "tsk_new_encrypted_value_99"
        )

    check("12. Legacy plaintext re-encrypted on rotate", c12)

    # ── 13. CodeQL py/regex-injection: metacharacter service names -> 400
    def c13():
        bad = ["FOO.*", "a)$", "svc; rm -rf /", "a b", "../escape", "1digit", "", "x" * 65]
        for name in bad:
            r = client.post(
                "/api/admin/keys/set",
                json={"service": name, "key": "tsk_abcdefghijklmnop1234"},
                headers={"X-API-Key": "owner-key-123"},
            )
            assert r.status_code == 400, f"service={name!r} -> {r.status_code}, expected 400"
        # Valid names must still pass through the gate (not over-blocking).
        from app.platform.key_manager import validate_service_name

        for ok in ("typesafe", "openai", "GOOGLE_MAPS", "a", "svc_1"):
            assert validate_service_name(ok) == ok

    check("13. Unsafe service names rejected (regex-injection closed)", c13)

    # ── 14. deploy_to_env: backslash-bearing value written literally
    def c14():
        from pathlib import Path as RealPath

        from app.platform.key_manager import KeyManagerAgent

        env_file = Path(workdir) / "deploy_target.env"
        env_file.write_text("EXISTING=1\nMYAPP_API_KEY=old\n")

        weird = r"tok\g<1>en\\with\backslashes"
        km_mod.KEYS_FILE = Path(workdir) / "deploy_keys.json"
        km_mod._key_manager = None
        kmgr = KeyManagerAgent()
        kmgr.set_key("myapp", weird)

        original_path = km_mod.Path
        km_mod.Path = lambda p: env_file if str(p) == "/opt/leadgen/.env" else original_path(p)
        try:
            res = kmgr.deploy_to_env("myapp")
        finally:
            km_mod.Path = original_path

        assert res.get("success") is True, res
        written = env_file.read_text()
        assert f"MYAPP_API_KEY={weird}" in written, f"value not written literally: {written!r}"
        assert "MYAPP_API_KEY=old" not in written, "old value not replaced"
        assert "EXISTING=1" in written, "unrelated line dropped"
        km_mod.KEYS_FILE = Path(keys_file)
        km_mod._key_manager = None

    check("14. deploy_to_env writes backslash values literally", c14)

    # ── summary
    print("\n" + "=" * 64)
    failed = 0
    for status, name, detail in results:
        mark = "✅" if status == PASS else "❌"
        print(f"{mark} {name}")
        if detail:
            print(f"     {detail}")
            failed += 1
    print("=" * 64)
    print(f"{len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
