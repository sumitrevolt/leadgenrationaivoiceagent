import os

import pytest

from app.telephony.trunks import list_active_trunks


def test_jio_sip_readiness_no_creds():
    # Ensure JIO is not listed if env vars are missing
    os.environ.clear()
    trunks = list_active_trunks()
    for t in trunks:
        assert t.name != "jio_mobile"

def test_jio_sip_readiness_with_creds_but_disabled():
    os.environ.update({
        "JIO_SIP_HOST": "sip.jio.in",
        "JIO_SIP_USER": "user",
        "JIO_SIP_PASS": "pass",
        "JIO_SIP_DID": "+919999999999",
        "JIO_TRUNK_ENABLED": "0"
    })
    trunks = list_active_trunks()
    for t in trunks:
        assert t.name != "jio_mobile"

def test_jio_sip_readiness_fully_enabled():
    os.environ.update({
        "JIO_SIP_HOST": "sip.jio.in",
        "JIO_SIP_USER": "user",
        "JIO_SIP_PASS": "pass",
        "JIO_SIP_DID": "+919999999999",
        "JIO_TRUNK_ENABLED": "1"
    })
    trunks = list_active_trunks()
    jio_trunks = [t for t in trunks if t.name == "jio_mobile"]
    assert len(jio_trunks) == 1
    assert jio_trunks[0].enabled is True
    assert jio_trunks[0].caller_id == "+919999999999"
