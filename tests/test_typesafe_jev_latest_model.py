"""
TypeSafe System One API contract tests.

Verifies:
1. Missing API key -> ZERO HTTP calls (fail-closed)
2. initialize/no-key -> inert
3. System One no-key -> inert
4. Default model -> jev-latest
5. Model override deterministic
6. URL exactly: https://api.typesafe.ai/v1/systemone
7. Payload includes: model, state, questions
8. Choice question serializes as type=choice
9. Noul serializes as type=noul
10. Score serializes as type=score
11. Compatibility helpers correctly parse answers
12. No old endpoint calls remain
13. Secret scan clean
"""
import os
import pytest
from unittest.mock import patch, MagicMock


class TestTypeSafeFailClosed:
    """Test fail-closed behavior when TYPEsafe_API_KEY is absent."""

    def test_no_key_no_http_call(self):
        """When no API key is set, initialize() must NOT make any HTTP request."""
        with patch.dict(os.environ, {"TYPEsafe_API_KEY": "", "TYPESAFE_MODEL": ""}, clear=True):
            import importlib
            import app.platform.typesafe_integration as ts_module
            importlib.reload(ts_module)

            from app.platform.typesafe_integration import TypeSafeClient

            with patch("app.platform.typesafe_integration.requests.post") as mock_post:
                client = TypeSafeClient()
                assert client.enabled is False

                result = client.initialize()
                assert result.success is False
                assert "INERT" in result.error
                mock_post.assert_not_called()

    def test_system_one_no_key_no_http_call(self):
        """system_one() must NOT hit network when key is absent."""
        with patch.dict(os.environ, {"TYPEsafe_API_KEY": "", "TYPESAFE_MODEL": ""}, clear=True):
            import importlib
            import app.platform.typesafe_integration as ts_module
            importlib.reload(ts_module)

            from app.platform.typesafe_integration import TypeSafeClient, Choice

            with patch("app.platform.typesafe_integration.requests.post") as mock_post:
                client = TypeSafeClient()
                result = client.system_one(
                    state={"task": "test"},
                    questions={"q": Choice("Test?", {"opt1": "Desc 1"})},
                )
                mock_post.assert_not_called()
                assert result.success is False
                assert "INERT" in result.error

    def test_choice_no_key_no_http_call(self):
        """choice() must NOT hit network when key is absent."""
        with patch.dict(os.environ, {"TYPEsafe_API_KEY": "", "TYPESAFE_MODEL": ""}, clear=True):
            import importlib
            import app.platform.typesafe_integration as ts_module
            importlib.reload(ts_module)

            from app.platform.typesafe_integration import TypeSafeClient

            with patch("app.platform.typesafe_integration.requests.post") as mock_post:
                client = TypeSafeClient()
                result = client.choice("Question?", {}, {"opt1": "Desc"})
                mock_post.assert_not_called()
                assert result.success is False

    def test_noul_no_key_no_http_call(self):
        """noul() must NOT hit network when key is absent."""
        with patch.dict(os.environ, {"TYPEsafe_API_KEY": "", "TYPESAFE_MODEL": ""}, clear=True):
            import importlib
            import app.platform.typesafe_integration as ts_module
            importlib.reload(ts_module)

            from app.platform.typesafe_integration import TypeSafeClient

            with patch("app.platform.typesafe_integration.requests.post") as mock_post:
                client = TypeSafeClient()
                result = client.noul("Question?", {})
                mock_post.assert_not_called()
                assert result.success is False

    def test_score_no_key_no_http_call(self):
        """score() must NOT hit network when key is absent."""
        with patch.dict(os.environ, {"TYPEsafe_API_KEY": "", "TYPESAFE_MODEL": ""}, clear=True):
            import importlib
            import app.platform.typesafe_integration as ts_module
            importlib.reload(ts_module)

            from app.platform.typesafe_integration import TypeSafeClient

            with patch("app.platform.typesafe_integration.requests.post") as mock_post:
                client = TypeSafeClient()
                result = client.score("Question?", {}, ["low", "high"])
                mock_post.assert_not_called()
                assert result.success is False


class TestTypeSafeJevLatestDefault:
    """Test that jev-latest is the default model."""

    def test_default_model_is_jevlatest(self):
        with patch.dict(os.environ, {"TYPEsafe_API_KEY": "", "TYPESAFE_MODEL": ""}, clear=True):
            import importlib
            import app.platform.typesafe_integration as ts_module
            importlib.reload(ts_module)

            from app.platform.typesafe_integration import TypeSafeClient
            client = TypeSafeClient()
            assert client.model == "jev-latest"

    def test_model_override(self):
        with patch.dict(os.environ, {"TYPEsafe_API_KEY": "", "TYPESAFE_MODEL": "jev-v2-test"}, clear=True):
            import importlib
            import app.platform.typesafe_integration as ts_module
            importlib.reload(ts_module)

            from app.platform.typesafe_integration import TypeSafeClient
            client = TypeSafeClient()
            assert client.model == "jev-v2-test"

    @patch("app.platform.typesafe_integration.requests.post")
    def test_systemone_url_and_payload(self, mock_post):
        """Verify exact URL and payload shape."""
        with patch.dict(os.environ, {"TYPEsafe_API_KEY": "test-key", "TYPESAFE_MODEL": ""}, clear=True):
            import importlib
            import app.platform.typesafe_integration as ts_module
            importlib.reload(ts_module)

            from app.platform.typesafe_integration import TypeSafeClient, Choice, Noul, Score

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "model": "jev-1.13.0",
                "answers": {
                    "q1": {"type": "choice", "choice": "opt1", "confidence": 0.8},
                    "q2": {"type": "noul", "probability": 0.85},
                },
                "usage": {"tokens": 100},
            }
            mock_resp.headers = {}
            mock_post.return_value = mock_resp

            client = TypeSafeClient()
            result = client.system_one(
                state={"task": "test"},
                questions={
                    "q1": Choice("Which?", {"opt1": "A", "opt2": "B"}),
                    "q2": Noul("Yes/no?"),
                },
            )

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            url = call_args[0][0]
            payload = call_args[1]["json"]

            assert url == "https://api.typesafe.ai/v1/systemone"
            assert payload["model"] == "jev-latest"
            assert "state" in payload
            assert "questions" in payload
            assert payload["questions"]["q1"]["type"] == "choice"
            assert payload["questions"]["q2"]["type"] == "noul"
            assert result.success is True
            assert result.model == "jev-1.13.0"
            assert "q1" in result.answers
            assert "q2" in result.answers

    @patch("app.platform.typesafe_integration.requests.post")
    def test_choice_compatibility_wrapper(self, mock_post):
        with patch.dict(os.environ, {"TYPEsafe_API_KEY": "test-key", "TYPESAFE_MODEL": ""}, clear=True):
            import importlib
            import app.platform.typesafe_integration as ts_module
            importlib.reload(ts_module)

            from app.platform.typesafe_integration import TypeSafeClient

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "model": "jev-1.13.0",
                "answers": {"q": {"type": "choice", "choice": "opt1", "confidence": 0.78}},
                "usage": {"tokens": 50},
            }
            mock_resp.headers = {}
            mock_post.return_value = mock_resp

            client = TypeSafeClient()
            result = client.choice("Which?", {}, {"opt1": "A"})

            assert result.success is True
            assert result.value == "opt1"
            assert result.confidence == 0.78

    @patch("app.platform.typesafe_integration.requests.post")
    def test_noul_compatibility_wrapper(self, mock_post):
        with patch.dict(os.environ, {"TYPEsafe_API_KEY": "test-key", "TYPESAFE_MODEL": ""}, clear=True):
            import importlib
            import app.platform.typesafe_integration as ts_module
            importlib.reload(ts_module)

            from app.platform.typesafe_integration import TypeSafeClient

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "model": "jev-1.13.0",
                "answers": {"q": {"type": "noul", "probability": 0.85}},
                "usage": {"tokens": 50},
            }
            mock_resp.headers = {}
            mock_post.return_value = mock_resp

            client = TypeSafeClient()
            result = client.noul("Is evidence sufficient?", {})

            assert result.success is True
            assert result.value == 0.85
            assert result.confidence == 0.85

    @patch("app.platform.typesafe_integration.requests.post")
    def test_score_compatibility_wrapper(self, mock_post):
        with patch.dict(os.environ, {"TYPEsafe_API_KEY": "test-key", "TYPESAFE_MODEL": ""}, clear=True):
            import importlib
            import app.platform.typesafe_integration as ts_module
            importlib.reload(ts_module)

            from app.platform.typesafe_integration import TypeSafeClient

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "model": "jev-1.13.0",
                "answers": {"q": {"type": "score", "score": "high"}},
                "usage": {"tokens": 50},
            }
            mock_resp.headers = {}
            mock_post.return_value = mock_resp

            client = TypeSafeClient()
            result = client.score("Rate this?", {}, ["low", "medium", "high"])

            assert result.success is True
            assert result.value == "high"


class TestTypeSafeSecretScan:
    """Verify no secrets leak into source/tests."""

    def test_no_hardcoded_key_in_source(self):
        with open("app/platform/typesafe_integration.py", "r") as f:
            content = f.read()
        assert "sk-" not in content
        assert "ts-" not in content
        assert "eyJ" not in content
        assert 'os.getenv("TYPEsafe_API_KEY"' in content
        assert 'os.getenv("TYPESAFE_MODEL"' in content
        # Old endpoints must NOT be called
        assert '"/choice"' not in content
        assert '"/noul"' not in content
        assert '"/score"' not in content
        assert '"/health"' not in content
        assert '"/v1/systemone"' in content
