"""Stdlib-only fake MCP + OpenAI gateway for the isolated DSH image smoke test."""

from __future__ import annotations

import json
import signal
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

HOST = "0.0.0.0"
PORT = 8000
TEST_BEARER = "Bearer dsh-smoke-token-placeholder"  # nosecret: fixed test placeholder


class GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: Any) -> None:
        # Never log request headers or bodies; the real token is sensitive.
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(HTTPStatus.OK, {"ok": True})
            return
        if self.path == "/v1/models":
            if not self._authorized():
                return
            self._json(
                HTTPStatus.OK,
                {"object": "list", "data": [{"id": "leadgen-free", "object": "model"}]},
            )
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        payload = self._read_json()
        if payload is None:
            return
        if self.path == "/mcp":
            self._mcp(payload)
            return
        if self.path == "/v1/chat/completions":
            self._chat(payload)
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def _authorized(self) -> bool:
        if self.path == "/health":
            return True
        if self.headers.get("Authorization") == TEST_BEARER:
            return True
        self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
        return False

    def _read_json(self) -> dict[str, Any] | None:
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 1_000_000:
                raise ValueError("invalid content length")
            value = json.loads(self.rfile.read(size))
            if not isinstance(value, dict):
                raise ValueError("body is not an object")
            return value
        except Exception:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return None

    def _mcp(self, payload: dict[str, Any]) -> None:
        method = payload.get("method")
        request_id = payload.get("id")
        if method == "notifications/initialized":
            self.send_response(HTTPStatus.ACCEPTED)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if method == "initialize":
            params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
            result = {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "leadgen-fake-mcp", "version": "1.0.0"},
            }
        elif method == "tools/list":
            result = {"tools": []}
        elif method == "ping":
            result = {}
        else:
            self._mcp_error(request_id, -32601, "method not found")
            return
        self._json(
            HTTPStatus.OK,
            {"jsonrpc": "2.0", "id": request_id, "result": result},
            extra_headers={"Mcp-Session-Id": "leadgen-smoke-session"},
        )

    def _mcp_error(self, request_id: Any, code: int, message: str) -> None:
        self._json(
            HTTPStatus.OK,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": code, "message": message},
            },
            extra_headers={"Mcp-Session-Id": "leadgen-smoke-session"},
        )

    def _chat(self, payload: dict[str, Any]) -> None:
        messages = payload.get("messages")
        serialized = json.dumps(messages, ensure_ascii=True) if isinstance(messages, list) else ""
        if "HANG_UNTIL_CANCELLED" in serialized:
            time.sleep(600)
            return
        if payload.get("stream") is True:
            chunks = [
                {
                    "id": "chatcmpl-smoke",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "leadgen-free",
                    "choices": [
                        {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
                    ],
                },
                {
                    "id": "chatcmpl-smoke",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "leadgen-free",
                    "choices": [
                        {"index": 0, "delta": {"content": "SMOKE_OK"}, "finish_reason": None}
                    ],
                },
                {
                    "id": "chatcmpl-smoke",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "leadgen-free",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    "usage": {
                        "prompt_tokens": 8,
                        "completion_tokens": 2,
                        "total_tokens": 10,
                    },
                },
            ]
            body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
            body += "data: [DONE]\n\n"
            self._bytes(HTTPStatus.OK, body.encode(), "text/event-stream")
            return
        self._json(
            HTTPStatus.OK,
            {
                "id": "chatcmpl-smoke",
                "object": "chat.completion",
                "created": 0,
                "model": "leadgen-free",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "SMOKE_OK"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10},
            },
        )

    def _json(
        self,
        status: HTTPStatus,
        value: dict[str, Any],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._bytes(
            status,
            json.dumps(value, separators=(",", ":")).encode(),
            "application/json",
            extra_headers=extra_headers,
        )

    def _bytes(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), GatewayHandler)

    def stop(_signum: int, _frame: Any) -> None:
        server.server_close()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    server.serve_forever(poll_interval=0.1)


if __name__ == "__main__":
    main()
