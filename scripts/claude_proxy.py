#!/usr/bin/env python3
"""
Claude-format model proxy in front of OmniRoute Gateway.

Sitting at http://127.0.0.1:22000
Advertises 12 Claude-prefixed OmniRoute combos (claude-omni-*) so Claude Desktop's
frontend filter passes all 12 dynamic combos into the UI dropdown.
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
UPSTREAM_KEY = os.environ.get("OMNIROUTE_API_KEY", "sk-18effe9c5f68c04f-b87d87-c952d5da")
LISTEN_HOST = os.environ.get("PROXY_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("PROXY_PORT", "22000"))

# 12 Claude-prefixed dynamic combos
ALL_COMBOS = [
    {
        "id": "claude-omni-coding-primary",
        "real": "leadgen-coding-primary",
        "name": "OmniRoute Coding Primary",
    },
    {
        "id": "claude-omni-coding-fast",
        "real": "leadgen-coding-fast",
        "name": "OmniRoute Coding Fast",
    },
    {
        "id": "claude-omni-repo-analysis",
        "real": "leadgen-repo-analysis",
        "name": "OmniRoute Repo Analysis",
    },
    {
        "id": "claude-omni-test-generation",
        "real": "leadgen-test-generation",
        "name": "OmniRoute Test Generation",
    },
    {"id": "claude-omni-agent-ops", "real": "leadgen-agent-ops", "name": "OmniRoute Agent Ops"},
    {"id": "claude-omni-swara-live", "real": "leadgen-swara-live", "name": "OmniRoute Swara Live"},
    {
        "id": "claude-omni-marketing-content",
        "real": "leadgen-marketing-content",
        "name": "OmniRoute Marketing Content",
    },
    {
        "id": "claude-omni-prospect-enrich",
        "real": "leadgen-prospect-enrich",
        "name": "OmniRoute Prospect Enrich",
    },
    {
        "id": "claude-omni-outreach-email",
        "real": "leadgen-outreach-email",
        "name": "OmniRoute Outreach Email",
    },
    {
        "id": "claude-omni-seo-keyword",
        "real": "leadgen-seo-keyword",
        "name": "OmniRoute SEO Keyword",
    },
    {
        "id": "claude-omni-governor-review",
        "real": "leadgen-governor-review",
        "name": "OmniRoute Governor Review",
    },
    {
        "id": "claude-omni-project-best",
        "real": "leadgen-project-best",
        "name": "OmniRoute Project Best",
    },
]

MODEL_MAP = {
    # 12 Claude-Prefixed OmniRoute Combos
    "claude-omni-coding-primary": "leadgen-coding-primary",
    "claude-omni-coding-fast": "leadgen-coding-fast",
    "claude-omni-repo-analysis": "leadgen-repo-analysis",
    "claude-omni-test-generation": "leadgen-test-generation",
    "claude-omni-agent-ops": "leadgen-agent-ops",
    "claude-omni-swara-live": "leadgen-swara-live",
    "claude-omni-marketing-content": "leadgen-marketing-content",
    "claude-omni-prospect-enrich": "leadgen-prospect-enrich",
    "claude-omni-outreach-email": "leadgen-outreach-email",
    "claude-omni-seo-keyword": "leadgen-seo-keyword",
    "claude-omni-governor-review": "leadgen-governor-review",
    "claude-omni-project-best": "leadgen-project-best",
    # Direct IDs
    "leadgen-coding-primary": "leadgen-coding-primary",
    "leadgen-coding-fast": "leadgen-coding-fast",
    "leadgen-repo-analysis": "leadgen-repo-analysis",
    "leadgen-test-generation": "leadgen-test-generation",
    "leadgen-agent-ops": "leadgen-agent-ops",
    "leadgen-swara-live": "leadgen-swara-live",
    "leadgen-marketing-content": "leadgen-marketing-content",
    "leadgen-prospect-enrich": "leadgen-prospect-enrich",
    "leadgen-outreach-email": "leadgen-outreach-email",
    "leadgen-seo-keyword": "leadgen-seo-keyword",
    "leadgen-governor-review": "leadgen-governor-review",
    "leadgen-project-best": "leadgen-project-best",
    # Standard Claude Aliases
    "claude-haiku-4-5": "leadgen-coding-fast",
    "claude-sonnet-4-5": "leadgen-coding-primary",
    "claude-opus-4-5-20250901": "leadgen-project-best",
    "claude-3-5-haiku-20241022": "leadgen-coding-fast",
    "claude-3-5-sonnet-20241022": "leadgen-coding-primary",
    "claude-opus-4-1": "leadgen-project-best",
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

    # 12 Claude-Prefixed Dynamic Combos (MANDATORY claude- prefix for Claude Desktop filter)
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
