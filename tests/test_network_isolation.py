"""RC5 — network isolation for the render step (T02 acceptance).

PRD acceptance criterion 6: an outbound call must FAIL during a render, and the
artifact must record *honestly* whether isolation was actually enforced.

What this suite proves, on THIS host and honestly:

  * ``build_isolation()`` is a never-raising, call-time decision whose ``enforced``
    flag is a truth value — True only when a real primitive (a netns prefix or the
    netless container) applied.
  * The fallback (a bare Windows host has no ``unshare``) degrades to
    ``proxy_blackhole`` with ``enforced=False`` and the artifact is labelled
    ``network_best_effort`` — never "hermetic".
  * ``_run_renderer`` actually APPLIES the decision: it prepends the argv prefix,
    black-holes the child's proxy environment, records ``network_isolation`` on its
    result, and — under ``CREATIVE_HYPERFRAMES_NETWORK_STRICT=1`` — refuses to
    render at all when isolation cannot be enforced.
  * Where a real namespace IS available (Linux container), a probe child's
    ``socket.connect()`` fails. That assertion is gated on the live probe and
    skipped where the primitive is unavailable, so the suite never claims more
    than the host can prove.

T07 (RC5 enforcement — the netless renderer) adds two more layers:

  * the **netless contract** — with ``CREATIVE_RENDER_NETLESS=1`` the decision is
    ``container_netns_none`` / ``enforced is True``, and the render-plane spool
    refuses to render on a bare flag: ``verify_netless()`` makes one real
    outbound connection and reports ``netless_verified`` only when it FAILS, so
    an unbacked netless claim is fail-closed, never labelled "hermetic";
  * the **netless enforcement** — the same egress probe run inside a
    ``docker run --network none`` container must FAIL. Where Docker cannot start
    a container (e.g. this Windows/Docker-Desktop host), that test SKIPS LOUDLY
    and names the branch that actually ran; it validates its own probe with a
    networked control run first, so it can never fake a pass.

Hermetic: no network, no renderer install, no app.main. The renderer subprocess is
a tiny local script, so the whole path runs on any platform. The single optional
exception is the container-enforcement test, which skips honestly where the host
cannot run containers.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.marketing.creative_os import hyperframes_provider as hf
from app.marketing.creative_os import network_guard as ng
from app.render_plane import spool


def _probe_child_src() -> str:
    """A one-liner child that tries to reach the internet and exits non-zero on success."""
    return (
        "import socket,sys\n"
        "try:\n"
        "    s=socket.create_connection(('1.1.1.1',443),timeout=3)\n"
        "    s.close()\n"
        "    sys.exit(0)   # egress SUCCEEDED -> isolation FAILED\n"
        "except Exception:\n"
        "    sys.exit(7)   # egress blocked -> isolation OK\n"
    )


class TestIsolationContract(unittest.TestCase):
    def test_build_isolation_never_raises_and_returns_contract(self):
        iso = ng.build_isolation()
        for key in ("method", "enforced", "argv_prefix", "env", "env_pop", "label", "probe"):
            self.assertIn(key, iso)
        self.assertIsInstance(iso["argv_prefix"], list)
        self.assertIsInstance(iso["enforced"], bool)

    def test_enforced_only_for_real_primitives(self):
        iso = ng.build_isolation()
        if iso["enforced"]:
            self.assertIn(iso["method"], (ng.METHOD_NETNS, ng.METHOD_CONTAINER_NETLESS))
            self.assertEqual(iso["label"], ng.LABEL_HERMETIC)
        else:
            self.assertEqual(iso["method"], ng.METHOD_PROXY_BLACKHOLE)
            self.assertEqual(iso["label"], ng.LABEL_BEST_EFFORT)

    def test_build_isolation_survives_a_broken_probe(self):
        with mock.patch.object(ng, "probe_netns", side_effect=RuntimeError("boom")):
            iso = ng.build_isolation()
        self.assertEqual(iso["method"], ng.METHOD_PROXY_BLACKHOLE)
        self.assertFalse(iso["enforced"])

    def test_netns_prefix_used_when_probe_succeeds(self):
        ok = {"available": True, "returncode": 0, "detail": "ok"}
        with mock.patch.object(ng, "probe_netns", return_value=ok):
            iso = ng.build_isolation()
        self.assertEqual(iso["method"], ng.METHOD_NETNS)
        self.assertTrue(iso["enforced"])
        self.assertEqual(iso["label"], ng.LABEL_HERMETIC)
        self.assertEqual(iso["argv_prefix"], [ng.unshare_path() or "unshare", "--net", "--"])

    def test_proxy_blackhole_when_probe_fails(self):
        bad = {"available": False, "returncode": 1, "detail": "returncode=1"}
        with mock.patch.object(ng, "probe_netns", return_value=bad):
            iso = ng.build_isolation()
        self.assertEqual(iso["method"], ng.METHOD_PROXY_BLACKHOLE)
        self.assertFalse(iso["enforced"])
        self.assertEqual(iso["label"], ng.LABEL_BEST_EFFORT)
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
            self.assertEqual(iso["env"][key], ng.BLACKHOLE_PROXY)
        self.assertIn("NO_PROXY", iso["env_pop"])

    def test_netless_fact_branch_is_enforced(self):
        with mock.patch.dict(os.environ, {ng.NETLESS_ENV: "1"}):
            iso = ng.build_isolation()
        self.assertEqual(iso["method"], ng.METHOD_CONTAINER_NETLESS)
        self.assertTrue(iso["enforced"])
        self.assertEqual(iso["label"], ng.LABEL_HERMETIC)

    def test_label_never_hermetic_when_unenforced(self):
        ev = ng.isolation_evidence({"method": ng.METHOD_PROXY_BLACKHOLE, "enforced": False})
        self.assertEqual(ev["label"], ng.LABEL_BEST_EFFORT)
        self.assertNotEqual(ev["label"], ng.LABEL_HERMETIC)

    def test_probe_facts_expose_the_rc5_triple(self):
        facts = ng.probe_facts()
        for key in ("unshare_present", "probe_returncode", "chosen_method", "enforced", "label"):
            self.assertIn(key, facts)
        self.assertEqual(facts["chosen_method"], ng.build_isolation()["method"])


class TestRunRendererAppliesIsolation(unittest.TestCase):
    """End-to-end wiring: the decision is actually applied to the child process."""

    def _fake_renderer_root(self, tmp: str) -> Path:
        root = Path(tmp)
        cli = root / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"
        cli.parent.mkdir(parents=True, exist_ok=True)
        # A real, local executable that dumps selected env to stdout and exits 0.
        cli.write_text(
            "import json, os, sys\n"
            "print(json.dumps({k: os.environ.get(k) for k in "
            "['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','HYPERFRAMES_API_KEY']}))\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        return root

    def test_run_renderer_records_isolation_and_blackholes_child_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._fake_renderer_root(tmp)
            out = Path(tmp) / "out.mp4"
            with mock.patch.object(hf, "renderer_root", return_value=root), mock.patch.object(
                hf, "_node_bin", return_value=sys.executable
            ), mock.patch.dict(os.environ, {"CREATIVE_HYPERFRAMES_NETWORK_DISABLED": "1"}):
                run = hf._run_renderer(
                    project_dir=Path(tmp),
                    manifest_path=Path(tmp) / "manifest.json",
                    output_path=out,
                    preset="1080p",
                    timeout_s=30,
                )
        self.assertIn("network_isolation", run)
        self.assertIn("isolation_label", run)
        ev = run["network_isolation"]
        self.assertIn(ev["method"], (ng.METHOD_NETNS, ng.METHOD_CONTAINER_NETLESS, ng.METHOD_PROXY_BLACKHOLE))
        # The child really received the isolation environment.
        child_env = json.loads(run["stdout_tail"])
        if ev["enforced"]:
            self.assertEqual(ev["label"], ng.LABEL_HERMETIC)
        else:
            self.assertEqual(ev["label"], ng.LABEL_BEST_EFFORT)
            self.assertEqual(child_env.get("HTTP_PROXY"), ng.BLACKHOLE_PROXY)
            self.assertEqual(child_env.get("HTTPS_PROXY"), ng.BLACKHOLE_PROXY)
        self.assertEqual(child_env.get("HYPERFRAMES_API_KEY"), "")

    def test_strict_mode_refuses_an_unenforced_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._fake_renderer_root(tmp)
            bad = {"available": False, "returncode": 1, "detail": "returncode=1"}
            env = {"CREATIVE_HYPERFRAMES_NETWORK_DISABLED": "1", ng.STRICT_ENV: "1"}
            with mock.patch.object(hf, "renderer_root", return_value=root), mock.patch.object(
                ng, "probe_netns", return_value=bad
            ), mock.patch.dict(os.environ, env):
                with self.assertRaises(hf.RenderError) as ctx:
                    hf._run_renderer(
                        project_dir=Path(tmp),
                        manifest_path=Path(tmp) / "manifest.json",
                        output_path=Path(tmp) / "out.mp4",
                        preset="1080p",
                        timeout_s=30,
                    )
        self.assertEqual(ctx.exception.code, "network_isolation_unavailable")

    def test_network_allowed_records_non_isolation_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._fake_renderer_root(tmp)
            with mock.patch.object(hf, "renderer_root", return_value=root), mock.patch.object(
                hf, "_node_bin", return_value=sys.executable
            ), mock.patch.dict(os.environ, {"CREATIVE_HYPERFRAMES_NETWORK_DISABLED": "0"}):
                run = hf._run_renderer(
                    project_dir=Path(tmp),
                    manifest_path=Path(tmp) / "manifest.json",
                    output_path=Path(tmp) / "out.mp4",
                    preset="1080p",
                    timeout_s=30,
                )
        self.assertEqual(run["network_isolation"]["method"], ng.METHOD_NETWORK_ALLOWED)
        self.assertFalse(run["network_isolation"]["enforced"])


class TestEgressActuallyFails(unittest.TestCase):
    """The PRD criterion itself — only provable where a real primitive exists."""

    def test_egress_fails_under_enforced_isolation(self):
        """Run the probe child UNDER the isolation primitive and assert egress dies.

        The probe runs as a real subprocess (so the repo's in-process test netguard
        does not mask it): ``rc == 7`` means ``connect()`` was refused, which is the
        PRD criterion. Gated on the live probe — on a host with no enforceable
        primitive there is nothing to prove, so we skip rather than fake it.
        """
        iso = ng.build_isolation()
        if not iso["enforced"]:
            self.skipTest(
                f"no enforceable primitive on {sys.platform}: method={iso['method']} "
                f"(unshare absent) — honest fallback, nothing to enforce"
            )
        argv = list(iso["argv_prefix"]) + [sys.executable, "-c", _probe_child_src()]
        env = ng.apply_isolation_env(dict(os.environ), iso)
        proc = subprocess.run(argv, env=env, capture_output=True, timeout=30, check=False)
        # rc==7 => connect() was refused (isolation works). rc==0 => it escaped.
        self.assertNotEqual(proc.returncode, 0, "an outbound connect() SUCCEEDED under enforced isolation")
        self.assertEqual(proc.returncode, 7, f"unexpected probe rc={proc.returncode}")


class TestNetlessRenderPlaneContract(unittest.TestCase):
    """T07 — the netless renderer is the RC5 *enforcement* primitive.

    Design §9.3 / §12-A3 mandate that the render run inside a ``network_mode: none``
    container, so ``build_isolation()`` returns ``container_netns_none`` with
    ``enforced is True``. These assertions run on every host and pin that contract
    — plus the honesty seam that makes the netless claim trustworthy: a bare
    ``CREATIVE_RENDER_NETLESS=1`` flag is NEVER accepted as proof on its own.
    """

    def test_netless_path_is_enforced_and_labelled_hermetic(self):
        with mock.patch.dict(os.environ, {ng.NETLESS_ENV: "1"}):
            iso = ng.build_isolation()
            ev = ng.isolation_evidence(iso)
        self.assertEqual(iso["method"], ng.METHOD_CONTAINER_NETLESS)
        self.assertEqual(iso["method"], "container_netns_none")
        self.assertTrue(iso["enforced"])
        self.assertEqual(iso["label"], ng.LABEL_HERMETIC)
        self.assertEqual(ev["method"], "container_netns_none")
        self.assertTrue(ev["enforced"])
        self.assertEqual(ev["label"], ng.LABEL_HERMETIC)

    def test_verify_netless_rejects_a_flag_without_a_real_block(self):
        """A flag is not proof: when egress still works, netless is UNVERIFIED."""
        with mock.patch.dict(os.environ, {ng.NETLESS_ENV: "1"}), mock.patch.object(
            spool, "_egress_blocked", return_value=(False, "egress_succeeded")
        ):
            check = spool.verify_netless()
        self.assertTrue(check["netless_requested"])
        self.assertFalse(check["netless_verified"])
        self.assertFalse(check["egress_blocked"])

    def test_verify_netless_accepts_a_real_block(self):
        """Only a real blocked connect() earns ``netless_verified is True``."""
        with mock.patch.dict(os.environ, {ng.NETLESS_ENV: "1"}), mock.patch.object(
            spool, "_egress_blocked", return_value=(True, "egress_blocked:OSError")
        ):
            check = spool.verify_netless()
        self.assertTrue(check["netless_requested"])
        self.assertTrue(check["netless_verified"])
        self.assertTrue(check["egress_blocked"])

    def test_verify_netless_without_the_flag_is_not_requested(self):
        env = {k: v for k, v in os.environ.items() if k != ng.NETLESS_ENV}
        with mock.patch.dict(os.environ, env, clear=True):
            check = spool.verify_netless()
        self.assertFalse(check["netless_requested"])
        self.assertFalse(check["netless_verified"])

    def test_drain_once_is_fail_closed_when_netless_is_unverified(self):
        """An unbacked netless claim must NOT render — fail-closed, no artifact."""
        calls: list[dict] = []
        with mock.patch.dict(os.environ, {ng.NETLESS_ENV: "1"}), mock.patch.object(
            spool, "_egress_blocked", return_value=(False, "egress_succeeded")
        ):
            out = spool.drain_once(lambda job: calls.append(job) or {"ok": True}, verify=True)
        self.assertFalse(out["ok"])
        self.assertEqual(out["outcome"], "netless_unverified")
        self.assertEqual(calls, [], "render_fn must not run when netless is unverified")

    def test_drain_once_renders_when_netless_is_verified(self):
        """With a real block asserted, the loop renders and records the isolation."""
        with tempfile.TemporaryDirectory() as root:
            env = {ng.NETLESS_ENV: "1", spool.SPOOL_ROOT_ENV: root}
            with mock.patch.dict(os.environ, env), mock.patch.object(
                spool, "_egress_blocked", return_value=(True, "egress_blocked:OSError")
            ):
                submitted = spool.submit({"job_id": "j1", "spec": {"x": 1}})
                self.assertTrue(submitted["ok"])
                artifact = Path(root) / "src_artifact.bin"
                artifact.write_bytes(b"rendered")
                out = spool.drain_once(
                    lambda job: {
                        "ok": True,
                        "artifact_path": str(artifact),
                        "network_isolation": ng.isolation_evidence(ng.build_isolation()),
                        "isolation_label": ng.isolation_label(ng.build_isolation()),
                    },
                    verify=True,
                )
        self.assertTrue(out["ok"])
        self.assertEqual(out["outcome"], "done")
        self.assertEqual(out["result"]["network_isolation"]["method"], "container_netns_none")
        self.assertTrue(out["result"]["network_isolation"]["enforced"])


class TestNetlessContainerEnforcement(unittest.TestCase):
    """The PRD criterion on the REAL primitive: egress dies in a netless container.

    ``docker run --network none`` gives the container no NIC at all, so a raw
    ``socket.connect()`` to the internet must fail. This is the only place the
    netless *enforcement* is proven end to end. Where Docker cannot actually start
    a container — e.g. this Windows / Docker-Desktop host, where ``docker run``
    hangs — the test SKIPS LOUDLY and names the branch that DID run (the in-process
    ``container_netns_none`` contract above). It never fakes a pass: it validates
    its own probe with a networked control run first, and only then trusts the
    netless result.

    Set ``CREATIVE_RENDER_DOCKER_IT=0`` to skip immediately (fast local runs);
    ``CREATIVE_RENDER_DOCKER_IT=1`` to require it (fail rather than skip).
    """

    #: Probe: try python3, then the shell ``/dev/tcp``, then busybox ``nc`` (scan
    #: then connect), then ``wget``. Exit 0 when an outbound connect SUCCEEDS,
    #: 7 when egress is blocked. The control run below validates whichever branch
    #: the image actually supports before the netless result is trusted.
    PROBE_SH = (
        "python3 -c \"import socket,sys\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1',443),timeout=3).close(); sys.exit(0)\n"
        "except Exception:\n"
        "    sys.exit(7)\" 2>/dev/null; rc=$?; { [ \"$rc\" = 0 ] || [ \"$rc\" = 7 ]; } && exit $rc\n"
        "(exec 3<>/dev/tcp/1.1.1.1/443) 2>/dev/null && exit 0\n"
        "command -v nc >/dev/null 2>&1 && nc -z -w 3 1.1.1.1 443 >/dev/null 2>&1 && exit 0\n"
        "command -v nc >/dev/null 2>&1 && nc -w 3 1.1.1.1 443 </dev/null >/dev/null 2>&1 && exit 0\n"
        "command -v wget >/dev/null 2>&1 && wget -T 3 -qO /dev/null http://1.1.1.1/ >/dev/null 2>&1 && exit 0\n"
        "exit 7\n"
    )

    #: Bounded so a host that cannot start containers fails fast instead of hanging.
    _TIMEOUT_S = 20

    def _probe(self, network: str, image: str):
        return subprocess.run(  # noqa: S603 - fixed argv, shell=False
            ["docker", "run", "--rm", "--network", network, image, "sh", "-c", self.PROBE_SH],
            capture_output=True,
            text=True,
            timeout=self._TIMEOUT_S,
            check=False,
        )

    def test_egress_fails_inside_a_netless_container(self):
        mode = (os.getenv("CREATIVE_RENDER_DOCKER_IT", "auto") or "auto").strip().lower()
        if mode == "0":
            self.skipTest(
                "CREATIVE_RENDER_DOCKER_IT=0 — container IT disabled by request; "
                "ran branch: in-process container_netns_none contract"
            )
        image = (os.getenv("CREATIVE_RENDER_IT_IMAGE", "") or "redis:7-alpine").strip()
        if shutil.which("docker") is None:
            self.skipTest(
                "docker binary absent — ran branch: in-process container_netns_none contract"
            )
        try:
            info = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001 - any failure is "docker not runnable"
            self.skipTest(
                f"docker not runnable ({type(exc).__name__}) — "
                f"ran branch: in-process container_netns_none contract"
            )
        if info.returncode != 0:
            self.skipTest(
                "docker daemon unreachable — ran branch: in-process container_netns_none contract"
            )

        # Control: WITH a network the probe MUST reach the internet. This proves the
        # probe + image are valid before we trust the netless result below.
        try:
            control = self._probe("bridge", image)
        except subprocess.TimeoutExpired:
            if mode == "1":
                self.fail("docker run hung — containers cannot start on this host")
            self.skipTest(
                "docker run hung — containers cannot start on this host — "
                "ran branch: in-process container_netns_none contract"
            )
        if control.returncode != 0:
            self.skipTest(
                f"probe could not reach the net even WITH network (rc={control.returncode}); "
                f"image {image} lacks a usable tool — ran branch: in-process contract"
            )

        # The RC5 criterion: egress must FAIL with no network interface at all.
        netless = self._probe("none", image)
        self.assertNotEqual(
            netless.returncode, 0, "an outbound connect() SUCCEEDED inside --network none"
        )
        self.assertEqual(netless.returncode, 7, f"unexpected netless probe rc={netless.returncode}")


class TestT05NetworkIsolationAcceptance(unittest.TestCase):
    """T05 acceptance for the isolation contract (design §2.5 / §9.3).

    Asserts, HONESTLY for whatever environment this host actually is:

      * ``build_isolation()`` reports the truth for the DETECTED environment. On a
        bare Windows box there is no ``unshare`` and no netless container, so it
        MUST degrade to ``proxy_blackhole`` / ``enforced is False``. We never
        hardcode ``enforced is True`` — that would be a fake-green on a host that
        cannot enforce anything.
      * The un-enforced fallback still black-holes egress and the child process
        receives that environment.

    The netless fact-branch (``CREATIVE_RENDER_NETLESS=1`` →
    ``container_netns_none`` / ``enforced is True``) is already pinned by T07's
    ``TestNetlessRenderPlaneContract`` above, so it is deliberately NOT duplicated
    here — a duplicate would inflate the count without adding coverage.

    This class is additive: it pins T05's acceptance without disturbing the
    T02/T07 contract classes above.
    """

    def _env_without_netless(self) -> dict[str, str]:
        return {k: v for k, v in os.environ.items() if k != ng.NETLESS_ENV}

    def test_detected_environment_is_reported_honestly(self):
        with mock.patch.dict(os.environ, self._env_without_netless(), clear=True):
            iso = ng.build_isolation()
            probe_ok = bool(ng.unshare_path()) and bool(ng.probe_netns().get("available"))
        if probe_ok:
            self.assertEqual(iso["method"], ng.METHOD_NETNS)
            self.assertTrue(iso["enforced"])
        else:
            self.assertEqual(iso["method"], ng.METHOD_PROXY_BLACKHOLE)
            self.assertFalse(iso["enforced"])
            self.assertEqual(iso["label"], ng.LABEL_BEST_EFFORT)

    def test_outbound_call_is_blackholed_when_unenforced(self):
        """The honest fallback still black-holes egress, and the child receives it."""
        bad = {"available": False, "returncode": 1, "detail": "returncode=1"}
        with mock.patch.dict(os.environ, self._env_without_netless(), clear=True), mock.patch.object(
            ng, "probe_netns", return_value=bad
        ):
            iso = ng.build_isolation()
            child = ng.apply_isolation_env({}, iso)
        self.assertEqual(iso["method"], ng.METHOD_PROXY_BLACKHOLE)
        self.assertFalse(iso["enforced"])
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
            self.assertEqual(child.get(key), ng.BLACKHOLE_PROXY)
        self.assertNotIn("NO_PROXY", child, "the blackhole must clear NO_PROXY")


class TestNetlessLabelRequiresProof(unittest.TestCase):
    """A2 — the ``hermetic`` label requires a VERIFIED block, never a bare flag.

    ``_run_renderer`` must not label an artifact ``hermetic`` on the strength of
    ``CREATIVE_RENDER_NETLESS=1`` alone: the netless claim is only trustworthy
    when the canonical egress probe proves egress is ACTUALLY blocked. These
    cases pin both directions — unverified ⇒ best-effort, verified ⇒ hermetic —
    so the fix cannot be satisfied by making the probe permanently pessimistic.
    """

    def _fake_renderer_root(self, tmp: str) -> Path:
        root = Path(tmp)
        cli = root / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"
        cli.parent.mkdir(parents=True, exist_ok=True)
        cli.write_text(
            "import json, os, sys\n"
            "print(json.dumps({k: os.environ.get(k) for k in ['HTTP_PROXY','NO_PROXY']}))\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        return root

    def _run(self, tmp: str, egress_blocked: tuple[bool, str]) -> dict:
        root = self._fake_renderer_root(tmp)
        env = {"CREATIVE_HYPERFRAMES_NETWORK_DISABLED": "1", ng.NETLESS_ENV: "1"}
        with mock.patch.object(hf, "renderer_root", return_value=root), mock.patch.object(
            hf, "_node_bin", return_value=sys.executable
        ), mock.patch.dict(os.environ, env), mock.patch.object(
            spool, "_egress_blocked", return_value=egress_blocked
        ):
            return hf._run_renderer(
                project_dir=Path(tmp),
                manifest_path=Path(tmp) / "manifest.json",
                output_path=Path(tmp) / "out.mp4",
                preset="1080p",
                timeout_s=30,
            )

    def test_bare_netless_flag_without_a_real_block_is_not_hermetic(self):
        """flag set + egress still reachable ⇒ NO ``hermetic`` label (the A2 fix)."""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(tmp, (False, "egress_succeeded"))
        self.assertNotEqual(run["isolation_label"], ng.LABEL_HERMETIC, run)
        self.assertEqual(run["isolation_label"], ng.LABEL_BEST_EFFORT)
        self.assertFalse(run["network_isolation"]["enforced"])
        self.assertEqual(run["network_isolation"]["label"], ng.LABEL_BEST_EFFORT)
        self.assertFalse(run["isolation_verification"]["netless_verified"])
        self.assertTrue(run["isolation_verification"]["netless_requested"])

    def test_netless_flag_with_a_real_block_stays_hermetic(self):
        """Mirror: flag set AND a real blocked connect() ⇒ still ``hermetic``."""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(tmp, (True, "egress_blocked:OSError"))
        self.assertEqual(run["isolation_label"], ng.LABEL_HERMETIC)
        self.assertTrue(run["network_isolation"]["enforced"])
        self.assertEqual(run["network_isolation"]["method"], ng.METHOD_CONTAINER_NETLESS)
        self.assertTrue(run["isolation_verification"]["netless_verified"])

    def test_strict_mode_refuses_when_netless_is_unverified(self):
        """Fail-closed: strict + an unbacked netless claim must REFUSE, not ship."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._fake_renderer_root(tmp)
            env = {
                "CREATIVE_HYPERFRAMES_NETWORK_DISABLED": "1",
                ng.NETLESS_ENV: "1",
                ng.STRICT_ENV: "1",
            }
            with mock.patch.object(hf, "renderer_root", return_value=root), mock.patch.object(
                hf, "_node_bin", return_value=sys.executable
            ), mock.patch.dict(os.environ, env), mock.patch.object(
                spool, "_egress_blocked", return_value=(False, "egress_succeeded")
            ):
                with self.assertRaises(hf.RenderError) as ctx:
                    hf._run_renderer(
                        project_dir=Path(tmp),
                        manifest_path=Path(tmp) / "manifest.json",
                        output_path=Path(tmp) / "out.mp4",
                        preset="1080p",
                        timeout_s=30,
                    )
        self.assertEqual(ctx.exception.code, "network_isolation_unavailable")


if __name__ == "__main__":
    unittest.main()
