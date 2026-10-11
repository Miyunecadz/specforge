"""Locking, atomic writes and hash chains (BUILD_SPEC §5)."""

from __future__ import annotations

import json
import multiprocessing as mp
import os

from _lib import fsutil, hashing


def _append_worker(path: str, worker: int, count: int) -> None:
    for i in range(count):
        fsutil.append_line(path, json.dumps({"w": worker, "i": i}))


def _chain_worker(path: str, worker: int, count: int) -> None:
    for i in range(count):
        hashing.append_chained(path, {"w": worker, "i": i})


def test_parallel_appends_lose_nothing(tmp_path):
    path = str(tmp_path / "log.jsonl")
    procs = [mp.Process(target=_append_worker, args=(path, w, 150)) for w in range(8)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
        assert p.exitcode == 0
    lines = open(path).read().splitlines()
    assert len(lines) == 1200
    records = [json.loads(line) for line in lines]  # every line is intact JSON
    assert {(r["w"], r["i"]) for r in records} == {(w, i) for w in range(8) for i in range(150)}


def test_parallel_chained_appends_keep_a_valid_chain(tmp_path):
    path = str(tmp_path / "fetch_log.jsonl")
    procs = [mp.Process(target=_chain_worker, args=(path, w, 60)) for w in range(6)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    assert len(hashing.read_jsonl(path)) == 360
    assert hashing.verify_chain(path) == []


def test_stale_lock_from_dead_process_is_broken(tmp_path):
    target = tmp_path / "f.json"
    lock = fsutil.lock_path(target)
    import socket

    lock.write_text(json.dumps({"pid": 2 ** 22 + 12345, "host": socket.gethostname(), "t": 0}))
    with fsutil.file_lock(target, timeout=2):
        assert lock.exists()
    assert not lock.exists()


def test_live_lock_times_out(tmp_path):
    target = tmp_path / "f.json"
    import socket

    fsutil.lock_path(target).write_text(json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "t": 0}))
    import pytest

    with pytest.raises(fsutil.LockTimeout):
        with fsutil.file_lock(target, timeout=0.2, stale_after=60):
            pass


def test_atomic_write_leaves_no_temp_files(tmp_path):
    p = tmp_path / "a" / "b.json"
    fsutil.atomic_write_json(p, {"x": 1})
    fsutil.atomic_write_json(p, {"x": 2})
    assert json.loads(p.read_text()) == {"x": 2}
    assert [f.name for f in p.parent.iterdir()] == ["b.json"]


def test_chain_detects_edit_delete_and_insert(tmp_path):
    p = tmp_path / "c.jsonl"
    for i in range(5):
        hashing.append_chained(p, {"i": i})
    assert hashing.verify_chain(p) == []
    lines = p.read_text().splitlines()

    edited = list(lines)
    rec = json.loads(edited[2])
    rec["i"] = 99
    edited[2] = json.dumps(rec)
    p.write_text("\n".join(edited) + "\n")
    assert hashing.verify_chain(p)

    p.write_text("\n".join(lines[:2] + lines[3:]) + "\n")
    assert hashing.verify_chain(p)

    p.write_text("\n".join(lines[:2] + [lines[1]] + lines[2:]) + "\n")
    assert hashing.verify_chain(p)

    p.write_text("\n".join(lines) + "\n")
    assert hashing.verify_chain(p) == []
