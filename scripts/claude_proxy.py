#!/usr/bin/env python3
"""
Claude-format model proxy in front of OmniRoute Gateway.

Sitting at http://127.0.0.1:22000
Advertises 14 Claude-prefixed OmniRoute combos (claude-omni-*) for Claude-format API
clients configured at :22000 (Claude Code via start-claude-omniroute.ps1, WorkBuddy custom
provider, Hermes/OpenClaw/Verdant custom providers). Note: Claude Desktop does NOT consume
this proxy — it has no custom-endpoint support and stays on the Claude subscription.
Proxies all chat, completions, and messages requests to OmniRoute (http://127.0.0.1:20128/v1).
"""

import http.server
import json
import os
import socketserver
import sys
import urllib.error
import urllib.request
from http import HTTPStatus

UPSTREAM = os.environ.get("OMNI_UPSTREAM", "http://127.0.0.1:20128")
UPSTREAM_KEY = os.environ.get("OMNIROUTE_API_KEY", "")
LISTEN_HOST = os.environ.get("PROXY_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("PROXY_PORT", "22000"))

# 14 Claude-prefixed dynamic combos
ALL_COMBOS = [
    {"id": "claude-omni-coding-primary", "real": "leadgen-coding-primary", "canonical": "leadsgen combo 1", "name": "OmniRoute Coding Primary (Combo 1)"},
    {"id": "claude-omni-coding-fast", "real": "leadgen-coding-fast", "canonical": "leadsgen combo 2", "name": "OmniRoute Coding Fast (Combo 2)"},
    {"id": "claude-omni-repo-analysis", "real": "leadgen-repo-analysis", "canonical": "leadsgen combo 3", "name": "OmniRoute Repo Analysis (Combo 3)"},
    {"id": "claude-omni-test-generation", "real": "leadgen-test-generation", "canonical": "leadsgen combo 4", "name": "OmniRoute Test Generation (Combo 4)"},
    {"id": "claude-omni-agent-ops", "real": "leadgen-agent-ops", "canonical": "leadsgen combo 5", "name": "OmniRoute Agent Ops (Combo 5)"},
    {"id": "claude-omni-swara-live", "real": "leadgen-swara-live", "canonical": "leadsgen combo 6", "name": "OmniRoute Swara Live (Combo 6)"},
    {"id": "claude-omni-marketing-content", "real": "leadgen-marketing-content", "canonical": "leadsgen combo 7", "name": "OmniRoute Marketing Content (Combo 7)"},
    {"id": "claude-omni-prospect-enrich", "real": "leadgen-prospect-enrich", "canonical": "leadsgen combo 8", "name": "OmniRoute Prospect Enrich (Combo 8)"},
    {"id": "claude-omni-outreach-email", "real": "leadgen-outreach-email", "canonical": "leadsgen combo 9", "name": "OmniRoute Outreach Email (Combo 9)"},
    {"id": "claude-omni-seo-keyword", "real": "leadgen-seo-keyword", "canonical": "leadsgen combo 10", "name": "OmniRoute SEO Keyword (Combo 10)"},
    {"id": "claude-omni-governor-review", "real": "leadgen-governor-review", "canonical": "leadsgen combo 11", "name": "OmniRoute Governor Review (Combo 11)"},
    {"id": "claude-omni-project-best", "real": "leadgen-project-best", "canonical": "leadsgen combo 12", "name": "OmniRoute Project Best (Combo 12)"},
    {"id": "claude-omni-free-first", "real": "leadgen-14th-combo", "canonical": "leadsgen combo 13", "name": "OmniRoute Free First VPS (Combo 13)"},
    {"id": "claude-omni-general", "real": "leadsgen-combo-14", "canonical": "leadsgen combo 14", "name": "OmniRoute General Purpose (Combo 14)"},
]

MODEL_MAP = {
    # 14 Claude-Prefixed OmniRoute Combos
    "claude-omni-coding-primary": "leadsgen combo 1",
    "claude-omni-coding-fast": "leadsgen combo 2",
    "claude-omni-repo-analysis": "leadsgen combo 3",
    "claude-omni-test-generation": "leadsgen combo 4",
    "claude-omni-agent-ops": "leadsgen combo 5",
    "claude-omni-swara-live": "leadsgen combo 6",
    "claude-omni-marketing-content": "leadsgen combo 7",
    "claude-omni-prospect-enrich": "leadsgen combo 8",
    "claude-omni-outreach-email": "leadsgen combo 9",
    "claude-omni-seo-keyword": "leadsgen combo 10",
    "claude-omni-governor-review": "leadsgen combo 11",
    "claude-omni-project-best": "leadsgen combo 12",
    "claude-omni-free-first": "leadsgen combo 13",
    "claude-omni-general": "leadsgen combo 14",
    # Direct Canonical IDs
    "leadsgen combo 1": "leadsgen combo 1",
    "leadsgen combo 2": "leadsgen combo 2",
    "leadsgen combo 3": "leadsgen combo 3",
    "leadsgen combo 4": "leadsgen combo 4",
    "leadsgen combo 5": "leadsgen combo 5",
    "leadsgen combo 6": "leadsgen combo 6",
    "leadsgen combo 7": "leadsgen combo 7",
    "leadsgen combo 8": "leadsgen combo 8",
    "leadsgen combo 9": "leadsgen combo 9",
    "leadsgen combo 10": "leadsgen combo 10",
    "leadsgen combo 11": "leadsgen combo 11",
    "leadsgen combo 12": "leadsgen combo 12",
    "leadsgen combo 13": "leadsgen combo 13",
    "leadsgen combo 14": "leadsgen combo 14",
    # Legacy leadgen-* IDs
    "leadgen-coding-primary": "leadsgen combo 1",
    "leadgen-coding-fast": "leadsgen combo 2",
    "leadgen-repo-analysis": "leadsgen combo 3",
    "leadgen-test-generation": "leadsgen combo 4",
    "leadgen-agent-ops": "leadsgen combo 5",
    "leadgen-swara-live": "leadsgen combo 6",
    "leadgen-marketing-content": "leadsgen combo 7",
    "leadgen-prospect-enrich": "leadsgen combo 8",
    "leadgen-outreach-email": "leadsgen combo 9",
    "leadgen-seo-keyword": "leadsgen combo 10",
    "leadgen-governor-review": "leadsgen combo 11",
    "leadgen-project-best": "leadsgen combo 12",
    "leadgen-14th-combo": "leadsgen combo 13",
    # Standard Claude Aliases
    "claude-haiku-4-5": "leadsgen combo 2",
    "claude-sonnet-4-5": "leadsgen combo 1",
    "claude-opus-4-5-20250901": "leadsgen combo 12",
    "claude-3-5-haiku-20241022": "leadsgen combo 2",
    "claude-3-5-sonnet-20241022": "leadsgen combo 1",
    "claude-opus-4-1": "leadsgen combo 12",
}


def normalize_path(path: str) -> str:
    """Normalize path by stripping duplicate /v1 prefixes."""
    while "/v1/v1" in path:
        path = path.replace("/v1/v1", "/v1")
    return path


def build_models_response():
    """Build a /v1/models response in Anthropic shape with claude-omni- prefixed IDs."""
    now = 1787911502
    data = []

    # 14 Claude-Prefixed Dynamic Combos (claude- prefix consumed by Claude-format clients)
    for combo in ALL_COMBOS:
        jls_extract_var = False
        data.append(
            {
                "id": combo["id"],
                "display_name": combo["name"],
                "object": "model",
                "created": now,
                "owned_by": "anthropic",
                "permission": [],
                "root": combo["id"],
                "parent": None,
                "context_length": 1048576,
                "max_input_tokens": 1048576,
                "max_output_tokens": 16384,
                "capabilities": {
                    "tool_calling": True,
                    "reasoning": True,
                    "thinking": True,
                    "temperature": True,
                },
            }
        )

    return {"object": "list", "data": data}


def rewrite_model_in_body(body_bytes: bytes, content_type: str) -> bytes:
    """Replace model references in JSON body with real OmniRoute IDs."""
    if not body_bytes or "json" not in content_type.lower():
        return body_bytes
    try:
        body = json.loads(body_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body_bytes
    changed = False
    if isinstance(body, dict):
        m = body.get("model")
        if isinstance(m, str) and m in MODEL_MAP:
            body["model"] = MODEL_MAP[m]
            changed = True
        meta = body.get("metadata")
        if isinstance(meta, dict) and isinstance(meta.get("model"), str):
            if meta["model"] in MODEL_MAP:
                meta["model"] = MODEL_MAP[meta["model"]]
                changed = True
    if changed:
        return json.dumps(body).encode("utf-8")
    return body_bytes


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    server_version = "ClaudeProxy/5.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[proxy] " + (fmt % args) + "\n")

    def _common_headers(self):
        return {
            "Authorization": f"Bearer {UPSTREAM_KEY}",
            "x-api-key": UPSTREAM_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": self.headers.get("Content-Type", "application/json"),
        }

    def _read_body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length > 0 else b""

    def _proxy_request(self, method, override_body=None):
        clean_path = normalize_path(self.path)
        url = UPSTREAM + clean_path
        body = override_body if override_body is not None else self._read_body()
        body = rewrite_model_in_body(body, self.headers.get("Content-Type", ""))

        headers_to_send = {
            k: v for k, v in self._common_headers().items() if v and k != "Content-Type"
        }
        req = urllib.request.Request(
            url,
            data=body if body else None,
            method=method,
            headers=headers_to_send,
        )
        if body and method != "GET":
            req.add_header("Content-Type", self.headers.get("Content-Type", "application/json"))

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                content_type = resp.headers.get("Content-Type", "")
                is_stream = "text/event-stream" in content_type.lower() or "chunked" in resp.headers.get("Transfer-Encoding", "").lower()

                try:
                    self.send_response(resp.status)
                    for k, v in resp.headers.items():
                        if k.lower() in (
                            "content-encoding",
                            "content-length",
                            "transfer-encoding",
                            "connection",
                        ):
                            continue
                        self.send_header(k, v)
                    self.send_header("Access-Control-Allow-Origin", "*")

                    if is_stream:
                        self.send_header("Transfer-Encoding", "chunked")
                        self.end_headers()
                        while True:
                            chunk = resp.read(512)
                            if not chunk:
                                break
                            # Write HTTP/1.1 chunked encoding
                            self.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n")
                            self.wfile.flush()
                        self.wfile.write(b"0\r\n\r\n")
                        self.wfile.flush()
                    else:
                        data = resp.read()
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        except urllib.error.HTTPError as e:
            data = e.read() if hasattr(e, "read") else b""
            try:
                self.send_response(e.code)
                for k, v in (e.headers or {}).items():
                    if k.lower() in (
                        "content-encoding",
                        "content-length",
                        "transfer-encoding",
                        "connection",
                    ):
                        continue
                    self.send_header(k, v)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
        except Exception as e:
            try:
                err = json.dumps(
                    {"error": {"message": f"proxy error: {e}", "type": "proxy_error"}}
                ).encode()
                self.send_response(HTTPStatus.BAD_GATEWAY)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err)))
                self.end_headers()
                self.wfile.write(err)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_HEAD(self):
        """Respond 200 OK to HEAD requests for health/discovery."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def do_GET(self):
        clean_path = normalize_path(self.path)
        path_without_query = clean_path.split("?")[0]

        if path_without_query.endswith("/models") or path_without_query in (
            "/v1/models",
            "/models",
        ):
            payload = json.dumps(build_models_response()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path_without_query in ("/health", "/_health", "/api/health"):
            payload = json.dumps(
                {"status": "ok", "upstream": UPSTREAM, "combos": [c["id"] for c in ALL_COMBOS]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        self._proxy_request("GET")

    def do_POST(self):
        self._proxy_request("POST")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def main():
    server = ThreadedHTTPServer((LISTEN_HOST, LISTEN_PORT), ProxyHandler)
    print(
        f"ClaudeProxy listening on http://{LISTEN_HOST}:{LISTEN_PORT} -> forwarding to {UPSTREAM}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down proxy.")
        server.server_close()


if __name__ == "__main__":
    main()
