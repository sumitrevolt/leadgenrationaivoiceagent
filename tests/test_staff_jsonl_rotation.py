"""W1.8 — unbounded JSONL stores must rotate (line-cap) in the kavya hygiene job.

Bug: `self_improve_runs.jsonl`, `content_feedback.jsonl`, `reply_drafts.jsonl` and
`content_queue/<id>.jsonl` were append-only with NO prune (kavya `run_ops` pruned only
DB events + transcript files) → unbounded disk growth on the 16GB VPS.

Fix: `_trim_jsonl` keeps the newest `max_lines` (atomic rewrite, best-effort) and
`_prune_jsonl_stores` trims all four stores; `run_ops` calls it alongside the existing
prunes.
"""

from __future__ import annotations

import app.agents.staff as staff


def _write_lines(path, n, key="i"):
    path.write_text("\n".join(f'{{"{key}":{i}}}' for i in range(n)) + "\n", encoding="utf-8")


def test_trim_jsonl_keeps_newest_n(tmp_path):
    p = tmp_path / "log.jsonl"
    _write_lines(p, 100)
    removed = staff._trim_jsonl(str(p), max_lines=10)
    lines = p.read_text(encoding="utf-8").splitlines()
    assert removed == 90
    assert len(lines) == 10
    assert lines[0] == '{"i":90}'  # newest 10 kept (90..99)
    assert lines[-1] == '{"i":99}'


def test_trim_jsonl_noop_when_within_cap(tmp_path):
    p = tmp_path / "small.jsonl"
    _write_lines(p, 3)
    assert staff._trim_jsonl(str(p), max_lines=10) == 0
    assert len(p.read_text(encoding="utf-8").splitlines()) == 3


def test_trim_jsonl_missing_file_is_zero(tmp_path):
    assert staff._trim_jsonl(str(tmp_path / "nope.jsonl"), max_lines=10) == 0


def test_prune_jsonl_stores_trims_files_and_queue_dir(tmp_path, monkeypatch):
    f1 = tmp_path / "self_improve_runs.jsonl"
    _write_lines(f1, 50)
    qdir = tmp_path / "content_queue"
    qdir.mkdir()
    fq = qdir / "client1.jsonl"
    _write_lines(fq, 40, key="j")

    monkeypatch.setattr(staff, "_JSONL_ROTATE_FILES", [str(f1)])
    monkeypatch.setattr(staff, "_JSONL_ROTATE_DIR", lambda: str(qdir))

    removed = staff._prune_jsonl_stores(max_lines=10)
    assert removed == (50 - 10) + (40 - 10)  # 40 + 30 = 70
    assert len(f1.read_text(encoding="utf-8").splitlines()) == 10
    assert len(fq.read_text(encoding="utf-8").splitlines()) == 10
