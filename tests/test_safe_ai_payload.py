"""Test safe_ai_payload: PII masking, secrets validation, provider blocking."""

import pytest
from app.platform.safe_ai_payload import (
    SafePayloadError,
    mask_customer_data,
    validate_no_secrets,
    block_if_sensitive,
    _mask_string,
    _mask_name,
    _mask_phone,
    _mask_email,
)


class TestMaskString:
    def test_mask_indian_phone(self):
        result = _mask_string("Call 9876543210 now")
        assert "[PHONE REDACTED]" in result

    def test_mask_phone_with_91_prefix(self):
        assert "[PHONE REDACTED]" in _mask_string("+91 98765 43210")

    def test_mask_email(self):
        assert (
            _mask_string("Email admin@leadsgenai.in for help") == "Email [EMAIL REDACTED] for help"
        )

    def test_mask_gstin(self):
        assert _mask_string("GST: 27AAPFU0939F1ZV") == "GST: [GST REDACTED]"

    def test_mask_pan(self):
        assert _mask_string("PAN: ABCPD1234E") == "PAN: [PAN REDACTED]"

    def test_mask_api_key(self):
        assert _mask_string("api_key = sk-abc123def456") == "[SECRET REDACTED]"

    def test_mask_github_token(self):
        assert (
            _mask_string("use ghp_abcdefghijklmnopqrstuvwxyz0123456789") == "use [SECRET REDACTED]"
        )

    def test_mask_facebook_token(self):
        result = _mask_string("access_token=EAAbc123def456ghi789")
        assert "[OAUTH REDACTED]" in result or "[SECRET REDACTED]" in result

    def test_mask_whatsapp_number(self):
        assert _mask_string("+919876543210@wa.gateway") == "[WHATSAPP REDACTED]"


class TestMaskName:
    def test_mask_full_name(self):
        assert _mask_name("Rahul Sharma") == "R***"

    def test_mask_single_letter(self):
        assert _mask_name("A") == "[NAME REDACTED]"

    def test_mask_empty(self):
        assert _mask_name("") == "[NAME REDACTED]"


class TestMaskPhone:
    def test_mask_10_digit(self):
        assert _mask_phone("9876543210") == "XXXX3210"

    def test_mask_with_country_code(self):
        assert _mask_phone("+91 9876543210") == "XXXX3210"

    def test_mask_short(self):
        assert _mask_phone("123") == "[PHONE REDACTED]"


class TestMaskEmail:
    def test_mask_normal_email(self):
        assert _mask_email("sunny@leadsgenai.in") == "redacted@leadsgenai.in"

    def test_mask_short_email(self):
        assert _mask_email("a@b") == "[EMAIL REDACTED]"


class TestMaskCustomerData:
    def test_mask_dict_with_known_fields(self):
        result = mask_customer_data(
            {
                "customer_name": "Rahul Sharma",
                "phone": "9876543210",
                "email": "rahul@example.com",
                "address": "Shop No 5, Nagpur",
                "gstin": "27AAPFU0939F1ZV",
                "description": "Good customer",
            }
        )
        assert result["customer_name"] == "R***"
        assert result["phone"] == "XXXX3210"
        assert result["email"] == "redacted@example.com"
        assert result["address"] == "[ADDRESS REDACTED]"
        assert result["gstin"] == "[GST REDACTED]"
        assert result["description"] == "Good customer"

    def test_mask_nested_dict(self):
        result = mask_customer_data(
            {
                "client": {
                    "name": "Rahul Sharma",
                    "contact": {"phone": "9876543210", "email": "test@test.com"},
                }
            }
        )
        assert result["client"]["name"] == "R***"
        assert result["client"]["contact"]["phone"] == "XXXX3210"
        assert result["client"]["contact"]["email"] == "redacted@test.com"

    def test_mask_list(self):
        result = mask_customer_data(
            [
                {"name": "Rahul", "phone": "9876543210"},
                {"name": "Priya", "phone": "9123456789"},
            ]
        )
        assert result[0]["name"] == "R***"
        assert result[0]["phone"] == "XXXX3210"

    def test_mask_string_direct(self):
        result = mask_customer_data("Call Rahul at 9876543210 or email rahul@test.com")
        assert "Rahul" not in result or "PHONE REDACTED" in result

    def test_mask_api_key_field(self):
        result = mask_customer_data({"api_key": "sk-mysecretkey123"})
        assert result["api_key"] == "[SECRET REDACTED]"


class TestValidateNoSecrets:
    def test_clean_payload_passes(self):
        validate_no_secrets({"text": "Hello, how are you?"})

    def test_secret_in_payload_fails(self):
        with pytest.raises(SafePayloadError):
            validate_no_secrets({"text": "api_key=sk-abc123"})

    def test_secret_in_string_fails(self):
        with pytest.raises(SafePayloadError):
            validate_no_secrets("My api key is sk-abc123def")


class TestBlockIfSensitive:
    def test_unsafe_provider_with_pii_blocks(self):
        payload = {"phone": "9876543210"}
        with pytest.raises(SafePayloadError, match="Cannot send customer PII"):
            block_if_sensitive(payload, "deepseek")

    @pytest.mark.parametrize("provider", ["opencode", "duckduckgo"])
    def test_no_auth_provider_with_pii_blocks(self, provider):
        """Opaque credential-free gateways must never receive customer PII."""
        with pytest.raises(SafePayloadError, match="Cannot send customer PII"):
            block_if_sensitive({"email": "customer@example.com"}, provider)

    def test_unsafe_provider_without_pii_passes(self):
        block_if_sensitive({"text": "generate a social media post"}, "qwen")

    def test_strict_provider_with_secret_blocks(self):
        with pytest.raises(SafePayloadError):
            block_if_sensitive({"api_key": "sk-abc123def456ghi789jkl012"}, "groq")

    def test_strict_provider_with_clean_data_passes(self):
        block_if_sensitive({"text": "analyze this code"}, "groq")

    def test_safe_provider_passes(self):
        block_if_sensitive({"customer_name": "Rahul", "description": "review this code"}, "claude")

    def test_unknown_provider_lowercase_handles(self):
        block_if_sensitive({"clean": "data"}, "invalid-provider")
