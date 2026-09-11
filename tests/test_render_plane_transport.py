"""Render-plane transport proofs (T02: resumable, hash-verified transfer).

The link between the local worker and the VPS drops, so an upload must resume by
byte offset and a received artifact must be verified by SHA-256 rather than
trusted. This suite proves the transport math:

  * ``plan_upload`` resumes from the FIRST unacknowledged chunk, normalising an
    out-of-order / duplicated / garbage acknowledgement list, and reports
    ``complete`` only when nothing is missing;
  * ``read_chunk`` → ``apply_chunk`` reassembles byte-identical content;
  * a chunk whose SHA-256 does not match is REJECTED, never silently written — so
    a corrupted transfer cannot be assembled into an artifact;
  * ``verify_artifact`` accepts a match and refuses a mismatch / missing /
    over-size artifact;
  * every entry returns a dict and never raises on garbage.

Hermetic: tmp files only, no network, no app.main.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from app.render_plane import transport as tp


class TestPlanUpload(unittest.TestCase):
    def test_plan_resumes_from_first_missing_chunk(self):
        # 3 x 4096-byte chunks; ack {0,2} -> next unacknowledged byte is chunk 1.
        plan = tp.plan_upload(4096 * 3, acknowledged=[0, 2], chunk=4096)
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["total_chunks"], 3)
        self.assertEqual(plan["missing"], [1])
        self.assertEqual(plan["next_offset"], 4096)
        self.assertFalse(plan["complete"])

    def test_plan_normalises_garbage_acknowledgements(self):
        plan = tp.plan_upload(4096 * 2, acknowledged=[1, 1, "x", None, 99, -1, 0], chunk=4096)
        self.assertEqual(plan["acknowledged"], [0, 1])
        self.assertTrue(plan["complete"])
        self.assertEqual(plan["next_offset"], 4096 * 2)

    def test_plan_empty_is_complete(self):
        plan = tp.plan_upload(0)
        self.assertEqual(plan["total_chunks"], 0)
        self.assertTrue(plan["complete"])

    def test_plan_never_raises_on_garbage(self):
        self.assertIsInstance(tp.plan_upload("nonsense"), dict)  # type: ignore[arg-type]


class TestChunkRoundTrip(unittest.TestCase):
    def _write(self, data: bytes) -> str:
        fd, path = tempfile.mkstemp()
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        return path

    def test_read_apply_reassembles_identical_bytes(self):
        payload = bytes(range(256)) * 40  # 10240 bytes
        path = self._write(payload)
        step = 4096
        buffer = bytearray()
        for offset in range(0, len(payload), step):
            chunk = tp.read_chunk(path, offset, chunk=step)
            self.assertTrue(chunk["ok"])
            applied = tp.apply_chunk(
                buffer, chunk["offset"], chunk["data"], expected_sha256=chunk["sha256"]
            )
            self.assertTrue(applied["ok"])
        self.assertEqual(bytes(buffer), payload)
        self.assertEqual(tp.sha256_bytes(bytes(buffer)), tp.sha256_file(path))

    def test_corrupt_chunk_is_rejected_not_written(self):
        buffer = bytearray(b"\x00" * 8)
        res = tp.apply_chunk(buffer, 0, b"payload", expected_sha256="0" * 64)
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "chunk_hash_mismatch")
        self.assertEqual(bytes(buffer), b"\x00" * 8, "a mismatched chunk must not be written")

    def test_read_chunk_reports_eof(self):
        path = self._write(b"abc")
        chunk = tp.read_chunk(path, 0, chunk=4096)
        self.assertTrue(chunk["eof"])
        self.assertEqual(chunk["length"], 3)


class TestVerifyArtifact(unittest.TestCase):
    def _write(self, data: bytes) -> str:
        fd, path = tempfile.mkstemp()
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        return path

    def test_accepts_a_matching_artifact(self):
        path = self._write(b"the real bytes")
        digest = tp.sha256_file(path)
        res = tp.verify_artifact(path, digest)
        self.assertTrue(res["ok"])
        self.assertEqual(res["sha256"], digest)
        self.assertEqual(res["bytes"], len(b"the real bytes"))

    def test_refuses_a_hash_mismatch(self):
        path = self._write(b"the real bytes")
        res = tp.verify_artifact(path, "f" * 64)
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "artifact_hash_mismatch")

    def test_refuses_missing_and_oversize(self):
        self.assertEqual(tp.verify_artifact("does/not/exist", "x")["error"], "artifact_missing")
        path = self._write(b"0123456789")
        res = tp.verify_artifact(path, tp.sha256_file(path), max_bytes=3)
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "artifact_too_large")

    def test_never_raises_on_garbage(self):
        self.assertIsInstance(tp.verify_artifact(None, "x"), dict)
        self.assertIsInstance(tp.describe_transfer(None), dict)
        # sha256_file returns "" for an unreadable path rather than raising.
        self.assertEqual(tp.sha256_file(None), "")


if __name__ == "__main__":
    unittest.main()
