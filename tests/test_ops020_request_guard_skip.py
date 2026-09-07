import os
from unittest.mock import MagicMock
from app.middleware import RequestGuardMiddleware

def test_request_guard_skip_defaults():
    # Unset env
    if "REQUEST_GUARD_SKIP" in os.environ:
        del os.environ["REQUEST_GUARD_SKIP"]
    app = MagicMock()
    middleware = RequestGuardMiddleware(app)
    assert "/ws" in middleware.skip
    assert "/health" in middleware.skip
    assert "/metrics" in middleware.skip
    assert "/api/voiceai" in middleware.skip
    assert "/api/web-call" in middleware.skip

def test_request_guard_skip_unions_custom_paths():
    os.environ["REQUEST_GUARD_SKIP"] = "/custom-job, /webhook/special"
    try:
        app = MagicMock()
        middleware = RequestGuardMiddleware(app)
        # Critical default paths MUST still be preserved (OPS-020)
        assert "/ws" in middleware.skip
        assert "/health" in middleware.skip
        assert "/metrics" in middleware.skip
        assert "/api/voiceai" in middleware.skip
        # Custom paths must also be included
        assert "/custom-job" in middleware.skip
        assert "/webhook/special" in middleware.skip
    finally:
        del os.environ["REQUEST_GUARD_SKIP"]
