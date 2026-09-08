"""Linux Docker smoke for the hardened DSH image on an internal-only network."""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
TEST_TOKEN = "dsh-smoke-token-placeholder"  # nosecret: fixed test placeholder
MAX_CANCEL_SECONDS = 5.0
ALLOWED_CONTAINER_ENV = {
    "DSH_RUN_TOKEN",
    "DSH_MCP_URL",
    "DSH_LLM_BASE_URL",
    "DSH_CORDIS_CONFIG",
    "HOME",
    "PATH",
    "SSL_CERT_FILE",
}


class SmokeFailure(RuntimeError):
    """Hardened runtime smoke contract failed."""


@dataclass
class JsonRpcProcess:
    process: subprocess.Popen[str]
    lines: queue.Queue[dict[str, Any]]
    stderr: list[str]
    backlog: list[dict[str, Any]] = field(default_factory=list)

    def send(self, payload: dict[str, Any]) -> None:
        if self.process.stdin is None:
            raise SmokeFailure("DSH stdin is unavailable")
        self.process.stdin.write(f"{json.dumps(payload, separators=(',', ':'))}\n")
        self.process.stdin.flush()

    def wait_for(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        *,
        timeout: float,
        label: str,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        observed: list[str] = []
        for index, message in enumerate(self.backlog):
            if predicate(message):
                return self.backlog.pop(index)
        while time.monotonic() < deadline:
            if self.process.poll() is not None and self.lines.empty():
                raise SmokeFailure(
                    f"DSH exited before {label}: rc={self.process.returncode}; "
                    f"stderr_lines={len(self.stderr)}"
                )
            try:
                message = self.lines.get(timeout=min(0.2, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                continue
            method = message.get("method")
            observed.append(str(method or f"id={message.get('id')}"))
            if predicate(message):
                return message
            self.backlog.append(message)
        raise SmokeFailure(f"timed out waiting for {label}; observed={observed[-8:]}")


def _run(*args: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
    )


def _start_runtime(image: str, network: str, name: str) -> JsonRpcProcess:
    command = [
        "docker",
        "run",
        "--name",
        name,
        "--network",
        network,
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=16m",  # nosec B108 -- isolated container tmpfs
        "--tmpfs",
        "/run/dsh:rw,noexec,nosuid,size=16m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "-i",
        "-e",
        f"DSH_RUN_TOKEN={TEST_TOKEN}",
        "-e",
        "DSH_MCP_URL=http://gateway:8000/mcp",
        "-e",
        "DSH_LLM_BASE_URL=http://gateway:8000/v1",
        "-e",
        "DSH_CORDIS_CONFIG=/usr/local/bin/cordis.yml",
        "-e",
        "HOME=/tmp",
        # pkg SEA: argv[1]=embedded script, argv[2]=user config path
        image,
        "/usr/local/bin/cordis.yml",
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    lines: queue.Queue[dict[str, Any]] = queue.Queue()
    stderr: list[str] = []

    def read_stdout() -> None:
        assert process.stdout is not None
        for raw in process.stdout:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                lines.put(value)

    def read_stderr() -> None:
        assert process.stderr is not None
        for raw in process.stderr:
            stderr.append(raw.rstrip())

    threading.Thread(target=read_stdout, daemon=True).start()
    threading.Thread(target=read_stderr, daemon=True).start()
    return JsonRpcProcess(process=process, lines=lines, stderr=stderr)


def _initialize(runtime: JsonRpcProcess, request_id: int = 1) -> None:
    runtime.send(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "cwd": "/run/dsh",
                "provider": "leadgen-internal",
                "model": "leadgen-free",
                "maxTokens": 64,
            },
        }
    )
    response = runtime.wait_for(
        lambda value: value.get("id") == request_id,
        timeout=30,
        label="initialize response",
    )
    if "error" in response:
        raise SmokeFailure("DSH initialize returned an error")


def _prompt(runtime: JsonRpcProcess, text: str, request_id: int = 2) -> None:
    runtime.send(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "session/prompt",
            "params": {
                "sessionId": f"smoke-{request_id}",
                "contentBlocks": [{"type": "text", "text": text}],
            },
        }
    )
    response = runtime.wait_for(
        lambda value: value.get("id") == request_id,
        timeout=20,
        label="prompt receipt",
    )
    if "error" in response:
        raise SmokeFailure("DSH prompt returned an error")


def _assert_env_allowlist(container: str) -> None:
    result = _run(
        "docker",
        "inspect",
        "--format",
        "{{range .Config.Env}}{{println .}}{{end}}",
        container,
        capture=True,
    )
    names = {line.split("=", 1)[0] for line in result.stdout.splitlines() if "=" in line}
    unexpected = sorted(names - ALLOWED_CONTAINER_ENV)
    if unexpected:
        raise SmokeFailure(f"DSH container received unexpected env names: {unexpected}")


def run_smoke(image: str, gateway_image: str) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:10]
    network = f"dsh-smoke-{suffix}"
    gateway = f"dsh-gateway-{suffix}"
    normal_name = f"dsh-normal-{suffix}"
    cancel_name = f"dsh-cancel-{suffix}"
    created: list[str] = []
    _run("docker", "network", "create", "--internal", network)
    try:
        _run(
            "docker",
            "run",
            "-d",
            "--name",
            gateway,
            "--network",
            network,
            "--network-alias",
            "gateway",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=8m",  # nosec B108 -- isolated container tmpfs
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            gateway_image,
        )
        created.append(gateway)
        _wait_gateway(gateway)

        normal = _start_runtime(image, network, normal_name)
        created.append(normal_name)
        _initialize(normal)
        _assert_env_allowlist(normal_name)
        _prompt(normal, "Reply exactly SMOKE_OK.")
        normal.wait_for(
            lambda value: (
                value.get("method") == "session.event"
                and "SMOKE_OK" in json.dumps(value.get("params"), ensure_ascii=True)
            ),
            timeout=45,
            label="fake model completion",
        )
        normal.send({"jsonrpc": "2.0", "id": 3, "method": "shutdown"})
        normal.wait_for(lambda value: value.get("id") == 3, timeout=10, label="shutdown response")
        shutdown_started = time.monotonic()
        normal.process.wait(timeout=MAX_CANCEL_SECONDS)
        shutdown_seconds = time.monotonic() - shutdown_started
        if normal.process.returncode != 0:
            raise SmokeFailure(f"clean shutdown returned {normal.process.returncode}")

        cancelled = _start_runtime(image, network, cancel_name)
        created.append(cancel_name)
        _initialize(cancelled, request_id=11)
        _prompt(cancelled, "HANG_UNTIL_CANCELLED", request_id=12)
        cancelled.wait_for(
            lambda value: (
                value.get("method") == "session.status"
                and value.get("params", {}).get("status") == "running"
            ),
            timeout=20,
            label="running state before hard cancellation",
        )
        cancel_started = time.monotonic()
        # Mirror app/tasks/dsh_jobs._terminate: soft TERM then escalate to KILL
        # inside the same 5s hard budget (MCP dispose can wedge on TERM alone).
        _run("docker", "kill", "--signal=TERM", cancel_name, check=False)
        try:
            cancelled.process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            _run("docker", "kill", "--signal=KILL", cancel_name, check=False)
            try:
                cancelled.process.wait(timeout=max(0.1, MAX_CANCEL_SECONDS - 2.0))
            except subprocess.TimeoutExpired as exc:
                raise SmokeFailure("DSH process did not terminate within five seconds") from exc
        cancel_seconds = time.monotonic() - cancel_started
        if cancel_seconds > MAX_CANCEL_SECONDS:
            raise SmokeFailure(f"DSH cancellation exceeded five seconds: {cancel_seconds:.3f}")

        return {
            "schema_version": 1,
            "network_mode": "docker_internal_only",
            "fake_model": "passed",
            "fake_mcp": "passed",
            "clean_shutdown_seconds": round(shutdown_seconds, 3),
            "hard_cancellation_seconds": round(cancel_seconds, 3),
            "child_env_names": sorted(ALLOWED_CONTAINER_ENV),
        }
    finally:
        for container in reversed(created):
            _run("docker", "rm", "-f", container, check=False)
        _run("docker", "network", "rm", network, check=False)


def _wait_gateway(container: str) -> None:
    deadline = time.monotonic() + 20
    probe = (
        "import urllib.request;"
        "r=urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=1);"
        "raise SystemExit(0 if r.status==200 else 1)"
    )
    while time.monotonic() < deadline:
        result = _run("docker", "exec", container, "python", "-c", probe, check=False)
        if result.returncode == 0:
            return
        time.sleep(0.2)
    raise SmokeFailure("fake gateway did not become healthy")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=os.getenv("DSH_IMAGE", "leadgen-dsh:test"))
    parser.add_argument(
        "--gateway-image",
        default=os.getenv("DSH_GATEWAY_IMAGE", "leadgen-dsh-gateway:test"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    proof = run_smoke(args.image, args.gateway_image)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{json.dumps(proof, indent=2, sort_keys=True)}\n", encoding="utf-8")
    print(
        "DSH_RUNTIME_SMOKE_OK "
        f"shutdown={proof['clean_shutdown_seconds']}s "
        f"cancel={proof['hard_cancellation_seconds']}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
