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
    fp = value_fingerprint("super-secret-value-xyz")
    assert fp["present"] is True
    assert fp["length"] == len("super-secret-value-xyz")
    assert "super" not in (fp["sha256_prefix"] or "")
    blob = str(fp)
    assert "super-secret" not in blob


def test_safe_probe_omits_secret_values():
    fake = SimpleNamespace(
        public_base_url="https://leadsgenai.in",
        vobiz_auth_token="LEAKME_TOKEN_VALUE",
        vobiz_sip_pass="LEAKME_SIP",
        database_url="postgresql://u:p@host/db",
        vobiz_auth_id="MA_example",
    )
    probe = safe_settings_probe(fake)
    text = str(probe)
    assert "LEAKME" not in text
    assert "postgresql://" not in text
    assert "vobiz_auth_token" in probe["secret_names_present"]
    assert "vobiz_sip_pass" in probe["secret_names_present"]
    assert "database_url" in probe["secret_names_present"]
    assert probe["fields"]["public_base_url"]["present"] is True
    assert "https://" not in str(probe["fields"]["public_base_url"])


def test_names_only_lists_attrs_without_values():
    fake = SimpleNamespace(public_base_url="https://x", vobiz_auth_token="t")
    names = settings_names_only(fake)
    assert "public_base_url" in names
    assert "vobiz_auth_token" in names
