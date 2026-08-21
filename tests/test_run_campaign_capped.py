"""_run_tasks_capped — the INC-56 per-seed wall-cap scheduler.

Ultrareview PR #3 (2026-08-21): a worker that dies natively (SIGSEGV in fplll /
MPFR / the g6k siever, or an external SIGKILL) bypasses the BaseException guard
in _seed_worker_to_queue, so nothing reaches the queue; previously it was
`del running[p]` and gone -- neither results nor killed, no log line, the wave
tally ended short with no trace. Now: a `crashed` bucket, a worker_crash event
in wall_cap_events.jsonl, and the invariant results+killed+crashed == tasks.
"""
import json
import os
import signal
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import run_campaign as rc  # noqa: E402

# task tuple shape consumed by the scheduler: (n, beta, seed, q, precision,
# max_tours, generator, seed_tag, ...)
def _task(seed):
    return (157, 40, seed, 2203, 500, 50, "ntru", "ntru_test")


def _fake_worker_factory(behaviour):
    """behaviour: seed -> 'ok' | 'segv' | 'exit1' | 'hang'."""
    def _worker(task):
        n, beta, seed = task[0], task[1], task[2]
        b = behaviour(seed)
        if b == "ok":
            return (n, beta, seed, 0.5, "ok")
        if b == "segv":
            os.kill(os.getpid(), signal.SIGSEGV)      # native crash, no except path
        if b == "exit1":
            os._exit(1)                               # hard exit, nothing enqueued
        if b == "hang":
            time.sleep(60)
        raise RuntimeError("unreachable")
    return _worker


@pytest.fixture
def events(tmp_path, monkeypatch):
    f = tmp_path / "wall_cap_events.jsonl"
    monkeypatch.setattr(rc, "_WALL_CAP_LOG_FILE", str(f))
    return f


def _read_events(f):
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def test_all_ok_tally_complete(events, monkeypatch):
    monkeypatch.setattr(rc, "_ntru_seed_worker", _fake_worker_factory(lambda s: "ok"))
    tasks = [_task(s) for s in range(4)]
    results, killed, crashed = rc._run_tasks_capped(tasks, nproc=2, seed_timeout_s=30)
    assert sorted(r[2] for r in results) == [0, 1, 2, 3]
    assert killed == [] and crashed == []
    assert _read_events(events) == []


def test_native_crash_lands_in_crashed_bucket_and_is_logged(events, monkeypatch):
    monkeypatch.setattr(rc, "_ntru_seed_worker",
                        _fake_worker_factory(lambda s: "segv" if s == 1 else "ok"))
    tasks = [_task(s) for s in range(3)]
    results, killed, crashed = rc._run_tasks_capped(tasks, nproc=3, seed_timeout_s=30)
    assert sorted(r[2] for r in results) == [0, 2]
    assert killed == []
    assert [c[0][2] for c in crashed] == [1]
    assert crashed[0][2] == -signal.SIGSEGV              # multiprocessing: -signum
    assert len(results) + len(killed) + len(crashed) == len(tasks)
    ev = _read_events(events)
    assert len(ev) == 1 and ev[0]["event"] == "worker_crash"
    assert ev[0]["seed"] == 1 and ev[0]["exitcode"] == -signal.SIGSEGV
    assert ev[0]["signal"] == "SIGSEGV"


def test_hard_exit_without_report_is_a_crash(events, monkeypatch):
    monkeypatch.setattr(rc, "_ntru_seed_worker",
                        _fake_worker_factory(lambda s: "exit1" if s == 0 else "ok"))
    tasks = [_task(s) for s in range(2)]
    results, killed, crashed = rc._run_tasks_capped(tasks, nproc=2, seed_timeout_s=30)
    assert [r[2] for r in results] == [1]
    assert [c[0][2] for c in crashed] == [0] and crashed[0][2] == 1
    assert _read_events(events)[0]["signal"] is None


def test_wall_cap_kill_still_separate_from_crash(events, monkeypatch):
    monkeypatch.setattr(rc, "_ntru_seed_worker",
                        _fake_worker_factory(lambda s: "hang" if s == 0 else "ok"))
    monkeypatch.setattr(rc, "_log_wall_cap_kill",
                        lambda task, el, cap: rc._append_seed_event(
                            {"event": "wall_cap_kill", "seed": task[2]}))
    tasks = [_task(s) for s in range(2)]
    results, killed, crashed = rc._run_tasks_capped(tasks, nproc=2, seed_timeout_s=1)
    assert [r[2] for r in results] == [1]
    assert [k[0][2] for k in killed] == [0]
    assert crashed == []                                   # a cap kill is NOT a crash
    assert [e["event"] for e in _read_events(events)] == ["wall_cap_kill"]
    assert len(results) + len(killed) + len(crashed) == len(tasks)
