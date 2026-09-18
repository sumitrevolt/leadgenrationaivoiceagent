"""
TypeSafe jev-latest model + fail-closed guard tests.

Verifies:
1. Missing API key → ZERO network calls (fail-closed)
2. initialize() returns unavailable/inert when key absent
3. Choice/Noul/Score do not hit network without key
4. jev-latest is the default model
5. TYPESAFE_MODEL override works
6. Secret scan remains clean (no keys in source)
"""
import os
import pytest
from unittest.mock import patch, MagicMock


class TestTypeSafeFailClosed:
    """Test fail-closed behavior when TYPEsafe_API_KEY is absent."""
    
    def test_no_key_no_network_call(self):
        """When no API key is set, initialize() must NOT make any network request."""
        # Ensure no key is set
        old_key = os.environ.pop("TYPEsafe_API_KEY", None)
        old_model = os.environ.pop("TYPESAFE_MODEL", None)
        
        try:
            # Mock requests.request to detect any network call
            with patch("app.platform.typesafe_integration.requests.request") as mock_request:
                from app.platform.typesafe_integration import TypeSafeClient
                
                client = TypeSafeClient()  # no key passed → uses env (unset)
                assert client.enabled is False, "Client should be disabled when key is absent"
                
                result = client.initialize()
                
                # MUST NOT call network
                mock_request.assert_not_called()
                
                # MUST return fail-closed response
                assert result.success is False
                assert "INERT" in result.error
                assert client._initialized is False
        finally:
            # Restore env
            if old_key is not None:
                os.environ["TYPEsafe_API_KEY"] = old_key
            if old_model is not None:
                os.environ["TYPESAFE_MODEL"] = old_model
    
    def test_choice_no_key_no_network_call(self):
        """choice() must NOT hit network when key is absent."""
        old_key = os.environ.pop("TYPEsafe_API_KEY", None)
        old_model = os.environ.pop("TYPESAFE_MODEL", None)
        
        try:
            with patch("app.platform.typesafe_integration.requests.request") as mock_request:
                from app.platform.typesafe_integration import TypeSafeClient
                
                client = TypeSafeClient()
                result = client.choice(
                    question="Test question",
                    state={"key": "value"},
                    criteria={"opt1": "Description 1", "opt2": "Description 2"}
                )
                
                mock_request.assert_not_called()
                assert result.success is False
                assert "INERT" in result.error
        finally:
            if old_key is not None:
                os.environ["TYPEsafe_API_KEY"] = old_key
            if old_model is not None:
                os.environ["TYPESAFE_MODEL"] = old_model
    
    def test_noul_no_key_no_network_call(self):
        """noul() must NOT hit network when key is absent."""
        old_key = os.environ.pop("TYPEsafe_API_KEY", None)
        old_model = os.environ.pop("TYPESAFE_MODEL", None)
        
        try:
            with patch("app.platform.typesafe_integration.requests.request") as mock_request:
                from app.platform.typesafe_integration import TypeSafeClient
                
                client = TypeSafeClient()
                result = client.noul(
                    question="Test question",
                    state={"key": "value"}
                )
                
                mock_request.assert_not_called()
                assert result.success is False
                assert "INERT" in result.error
        finally:
            if old_key is not None:
                os.environ["TYPEsafe_API_KEY"] = old_key
            if old_model is not None:
                os.environ["TYPESAFE_MODEL"] = old_model
    
    def test_score_no_key_no_network_call(self):
        """score() must NOT hit network when key is absent."""
        old_key = os.environ.pop("TYPEsafe_API_KEY", None)
        old_model = os.environ.pop("TYPESAFE_MODEL", None)
        
        try:
            with patch("app.platform.typesafe_integration.requests.request") as mock_request:
                from app.platform.typesafe_integration import TypeSafeClient
                
                client = TypeSafeClient()
                result = client.score(
                    question="Test question",
                    state={"key": "value"},
                    criteria=["low", "medium", "high"]
                )
                
                mock_request.assert_not_called()
                assert result.success is False
                assert "INERT" in result.error
        finally:
            if old_key is not None:
                os.environ["TYPEsafe_API_KEY"] = old_key
            if old_model is not None:
                os.environ["TYPESAFE_MODEL"] = old_model


class TestTypeSafeJevLatestDefault:
    """Test that jev-latest is the default model."""
    
    def test_default_model_is_jevlatest(self):
        """When TYPESAFE_MODEL is unset, default must be jev-latest."""
        old_model = os.environ.pop("TYPESAFE_MODEL", None)
        old_key = os.environ.pop("TYPEsafe_API_KEY", None)
        
        try:
            from app.platform.typesafe_integration import TypeSafeClient
            
            client = TypeSafeClient()
            assert client.model == "jev-latest", f"Expected jev-latest, got {client.model}"
        finally:
            if old_model is not None:
                os.environ["TYPESAFE_MODEL"] = old_model
            if old_key is not None:
                os.environ["TYPEsafe_API_KEY"] = old_key
    
    def test_typesafe_model_override(self):
        """When TYPESAFE_MODEL env var is set, client must use it."""
        old_model = os.environ.get("TYPESAFE_MODEL")
        old_key = os.environ.pop("TYPEsafe_API_KEY", None)
        
        try:
            os.environ["TYPESAFE_MODEL"] = "jev-v2-test"
            
            from app.platform.typesafe_integration import TypeSafeClient
            
            client = TypeSafeClient()
            assert client.model == "jev-v2-test", f"Expected jev-v2-test, got {client.model}"
        finally:
            if old_model is not None:
                os.environ["TYPESAFE_MODEL"] = old_model
            else:
                os.environ.pop("TYPESAFE_MODEL", None)
            if old_key is not None:
                os.environ["TYPEsafe_API_KEY"] = old_key
    
    @patch("app.platform.typesafe_integration.requests.request")
    def test_jevlatest_sent_in_payload(self, mock_request):
        """When key IS present, jev-latest must be sent in the request payload."""
        old_model = os.environ.get("TYPESAFE_MODEL")
        old_key = os.environ.pop("TYPEsafe_API_KEY", None)
        
        try:
            os.environ["TYPEsafe_API_KEY"] = "test-key-for-unit-test"
            os.environ.pop("TYPESAFE_MODEL", None)  # use default
            
            from app.platform.typesafe_integration import TypeSafeClient
            
            mock_response = MagicMock()
            mock_response.json.return_value = {"choice": "opt1", "confidence": 0.8}
            mock_response.raise_for_status = MagicMock()
            mock_request.return_value = mock_response
            
            client = TypeSafeClient()
            result = client.choice(
                question="Test",
                state={},
                criteria={"opt1": "Desc 1"}
            )
            
            # Verify network WAS called
            mock_request.assert_called_once()
            
            # Verify payload contains jev-latest
            call_args = mock_request.call_args
            payload = call_args[1]["json"]
            assert payload["model"] == "jev-latest", f"Expected jev-latest in payload, got {payload['model']}"
            
            assert result.success is True
            assert result.value == "opt1"
        finally:
            if old_model is not None:
                os.environ["TYPESAFE_MODEL"] = old_model
            else:
                os.environ.pop("TYPESAFE_MODEL", None)
            if old_key is not None:
                os.environ["TYPEsafe_API_KEY"] = old_key


class TestTypeSafeSecretScan:
    """Verify no secrets leak into source/tests."""
    
    def test_no_hardcoded_key_in_source(self):
        """Source file must not contain any hardcoded API key patterns."""
        with open("app/platform/typesafe_integration.py", "r") as f:
            content = f.read()
        
        # Should NOT contain any key-like patterns
        assert "sk-" not in content
        assert "ts-" not in content
        assert "eyJ" not in content  # JWT start
        
        # Should only contain env var reads
        assert 'os.getenv("TYPEsafe_API_KEY"' in content
        assert 'os.getenv("TYPESAFE_MODEL"' in content
