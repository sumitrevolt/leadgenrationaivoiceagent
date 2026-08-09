"""Guards against dumping Settings / credential values into logs or chat."""

from __future__ import annotations

from types import SimpleNamespace

from app.utils.safe_settings import (
    is_secret_field_name,
    safe_settings_probe,
    settings_names_only,
    value_fingerprint,
)


def test_secret_field_names_detected():
    assert is_secret_field_name("vobiz_auth_token")
    assert is_secret_field_name("vobiz_sip_pass")
    assert is_secret_field_name("database_url")
    assert is_secret_field_name("DATABASE_URL")
    assert not is_secret_field_name("public_base_url")
    assert not is_secret_field_name("vobiz_auth_id")


def test_fingerprint_never_echoes_value():
    sample = "val_" + ("z" * 20)
    fp = value_fingerprint(sample)
    assert fp["present"] is True
    assert fp["length"] == len(sample)
    assert sample not in (fp["sha256_prefix"] or "")
    blob = str(fp)
    assert sample not in blob


def test_safe_probe_omits_secret_values():
    # Build fake secrets at runtime so scanners do not treat fixtures as leaks.
    fake_token = "tok_" + ("a" * 24)
    fake_sip = "sip_" + ("b" * 24)
    fake_dsn = "postgresql://" + "u" + ":" + ("c" * 12) + "@host/db"
    fake = SimpleNamespace(
        public_base_url="https://leadsgenai.in",
        vobiz_auth_token=fake_token,
        vobiz_sip_pass=fake_sip,
        database_url=fake_dsn,
        vobiz_auth_id="MA_example",
    )
    probe = safe_settings_probe(fake)
    text = str(probe)
    assert fake_token not in text
    assert fake_sip not in text
    assert "postgresql://" not in text
    assert "vobiz_auth_token" in probe["secret_names_present"]
    assert "vobiz_sip_pass" in probe["secret_names_present"]
    assert "database_url" in probe["secret_names_present"]
    assert probe["fields"]["public_base_url"]["present"] is True
    assert "https://" not in str(probe["fields"]["public_base_url"])


def test_names_only_lists_attrs_without_values():
    fake = SimpleNamespace(
        public_base_url="https://example.invalid",
        vobiz_auth_token="tok_" + ("d" * 16),
    )
    names = settings_names_only(fake)
    assert "public_base_url" in names
    assert "vobiz_auth_token" in names


def test_unknown_field_is_default_denied():
    """Design power of safe_settings_probe: not on allowlist => dropped entirely."""
    marker = "SHOULD_NOT_APPEAR_" + ("e" * 12)
    fake = SimpleNamespace(
        public_base_url="https://example.invalid",
        some_brand_new_debug_field=marker,
    )
    probe = safe_settings_probe(fake)
    assert "some_brand_new_debug_field" not in probe["fields"]
    assert marker not in str(probe)
    # Allowlisted field still present as fingerprint only.
    assert "public_base_url" in probe["fields"]
    assert probe["fields"]["public_base_url"]["present"] is True
