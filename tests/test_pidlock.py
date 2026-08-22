"""_pidlock — the shared single-instance lock (ultrareview PR #3, 2026-08-21).

Covers both halves that the two in-script versions each lacked: atomic create
under a real multi-process race, and the anchored holder match (a recycled pid
running `tail -f`/`pytest` on the script file must NOT block a restart).
"""
import multiprocessing as mp
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import _pidlock  # noqa: E402

SCRIPT = "some_driver.py"


def _quiet(_msg):
    pass


def test_fresh_lock_acquired_and_holds_own_pid(tmp_path):
    lock = tmp_path / "x.lock"
    assert _pidlock.acquire_pidlock(lock, SCRIPT, _quiet) is True
    assert lock.read_text() == str(os.getpid())
    assert not list(tmp_path.glob(".*.tmp"))           # temp file cleaned up


def test_release_only_when_owner(tmp_path):
    lock = tmp_path / "x.lock"
    # NOT a literal "1": under `docker run ... python3 -m pytest` (how CI
    # invokes this) pytest IS pid 1, so "1" would be our own pid and the
    # release would legitimately fire. getpid()+1 can never equal getpid().
    lock.write_text(str(os.getpid() + 1))
    _pidlock.release_pidlock(lock)
    assert lock.exists()                                # not ours -> untouched
    lock.write_text(str(os.getpid()))
    _pidlock.release_pidlock(lock)
    assert not lock.exists()


def test_dead_pid_reclaimed(tmp_path):
    lock = tmp_path / "x.lock"
    # spawn+reap a child so we hold a pid that is guaranteed dead
    p = mp.get_context("fork").Process(target=lambda: None)
    p.start(); p.join()
    lock.write_text(str(p.pid))
    assert _pidlock.acquire_pidlock(lock, SCRIPT, _quiet) is True
    assert lock.read_text() == str(os.getpid())


def test_garbage_lock_reclaimed(tmp_path):
    lock = tmp_path / "x.lock"
    lock.write_text("")                                 # empty / partial write
    assert _pidlock.acquire_pidlock(lock, SCRIPT, _quiet) is True
    lock.write_text("not-a-pid")
    assert _pidlock.acquire_pidlock(lock, SCRIPT, _quiet) is True


def test_live_python_running_script_blocks(tmp_path, monkeypatch):
    lock = tmp_path / "x.lock"
    lock.write_text(str(os.getpid()))                   # this pytest = "alive"
    monkeypatch.setattr(Path, "read_bytes",
                        lambda self: b"/usr/bin/python3\0scripts/some_driver.py\0")
    msgs = []
    assert _pidlock.acquire_pidlock(lock, SCRIPT, msgs.append) is False
    assert lock.read_text() == str(os.getpid())         # untouched
    assert any("holds the lock" in m for m in msgs)


def test_recycled_pid_running_related_tool_reclaimed(tmp_path, monkeypatch):
    lock = tmp_path / "x.lock"
    for argv in (b"tail\0-f\0scripts/some_driver.py\0",
                 b"vim\0some_driver.py\0",
                 b"python3\0-m\0pytest\0tests/test_some_driver.py\0",
                 b"/usr/bin/python3\0scripts/other_driver.py\0"):
        lock.write_text(str(os.getpid()))               # alive pid, wrong program
        monkeypatch.setattr(Path, "read_bytes", lambda self, a=argv: a)
        assert _pidlock.acquire_pidlock(lock, SCRIPT, _quiet) is True, argv
        assert lock.read_text() == str(os.getpid())


def _self_cmdline():
    return [a for a in Path("/proc/self/cmdline").read_bytes().decode().split("\0") if a]


def _live_script_name():
    """A basename the REAL /proc/<pid>/cmdline of forked racers will match
    (children inherit this pytest's cmdline), so the winner counts as live."""
    argv = _self_cmdline()
    if not argv or "python" not in os.path.basename(argv[0]):
        pytest.skip("race test needs a python interpreter in argv[0]")
    return os.path.basename(argv[-1])


def _racer(lock_s, script, start, done, out):
    start.wait()
    ok = _pidlock.acquire_pidlock(Path(lock_s), script, _quiet)
    out.put((os.getpid(), ok))
    if ok:
        done.wait(60)        # stay alive (= a live holder) until everyone reported
        os._exit(0)          # leave the lock file as-is (winner's pid)


def _race(lock: Path, n: int = 12):
    script = _live_script_name()
    ctx = mp.get_context("fork")
    start, done, out = ctx.Event(), ctx.Event(), ctx.Queue()
    ps = [ctx.Process(target=_racer, args=(str(lock), script, start, done, out))
          for _ in range(n)]
    for p in ps:
        p.start()
    start.set()
    res = [out.get(timeout=30) for _ in ps]
    done.set()
    for p in ps:
        p.join(30)
    return [pid for pid, ok in res if ok]


def test_race_fresh_lock_exactly_one_winner(tmp_path):
    lock = tmp_path / "x.lock"
    winners = _race(lock)
    assert len(winners) == 1
    assert lock.read_text() == str(winners[0])


def test_race_stale_lock_exactly_one_reclaimer(tmp_path):
    # The TOCTOU the old onset_driver had: every racer sees the same stale pid
    # and tries to reclaim. Atomic create + retry must still yield ONE holder.
    lock = tmp_path / "x.lock"
    p = mp.get_context("fork").Process(target=lambda: None)
    p.start(); p.join()
    lock.write_text(str(p.pid))                         # stale: dead pid
    winners = _race(lock)
    assert len(winners) == 1
    assert lock.read_text() == str(winners[0])
