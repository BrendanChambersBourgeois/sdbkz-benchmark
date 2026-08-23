"""forever_runner — the reconciled minimal never-idle loop (B2 review).

Tests target exactly the review-flagged failure modes: stop-LOUD after repeated
failure (not churn), never raise out of the loop, no busy-spin path, filler
targets the least-sampled ntru_b2 cell, and the worklist is consumed via a
done-log (never rewritten, comments/blanks skipped, completed lines not retried).
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import forever_runner as fr  # noqa: E402


def _wire(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "REPO", tmp_path)
    monkeypatch.setattr(fr, "WORKLIST", tmp_path / "worklist.txt")
    monkeypatch.setattr(fr, "DONE_LOG", tmp_path / "worklist.done")
    monkeypatch.setattr(fr, "FAILED_LOG", tmp_path / "worklist.failed")


def test_worklist_skips_comments_blanks_and_done(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    (tmp_path / "worklist.txt").write_text(
        "# a comment\n\nntru_x --n 1\nntru_y --n 2\n")
    assert fr.next_worklist_line() == "ntru_x --n 1"
    fr._record(fr.DONE_LOG, 0, "ntru_x --n 1")
    assert fr.next_worklist_line() == "ntru_y --n 2"      # first not-done line
    fr._record(fr.DONE_LOG, 0, "ntru_y --n 2")
    assert fr.next_worklist_line() is None                # all done -> filler


def test_malformed_line_is_rc2_not_crash(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(fr, "_run_campaign", lambda *a, **k: 0)
    assert fr.run_worklist_line("@budget_h=1", dry=False) == 2   # no campaign token


def test_budget_suffix_parsed_and_stripped(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    seen = {}
    def fake(args, budget_h, dry):
        seen["args"], seen["budget_h"] = args, budget_h
        return 0
    monkeypatch.setattr(fr, "_run_campaign", fake)
    fr.run_worklist_line("ntru_wall_beta_bump --n 179 @budget_h=6", dry=False)
    assert seen["budget_h"] == 6.0
    assert "@budget_h=6" not in seen["args"] and "--n" in seen["args"]


def test_filler_targets_least_sampled_cell(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    # n=179 cell has the fewest seeds -> filler must pick it.
    for (n, q), k in zip(fr.FILLER_CELLS, (30, 20, 5), strict=True):
        d = tmp_path / "results" / "seeds" / "ntru_b2" / f"q{q}" / "p500_mt50" / f"n{n}_beta40"
        d.mkdir(parents=True)
        for i in range(k):
            (d / f"seed{i:04d}.json").write_text("{}")
    picked = {}
    def fake(args, budget_h, dry):
        picked["n"] = args[args.index("--n") + 1]
        return 0
    monkeypatch.setattr(fr, "_run_campaign", fake)
    assert fr.run_filler_unit(dry=False) is True
    assert picked["n"] == "179"                           # the 5-seed cell


def test_stop_loud_after_consecutive_failures_not_churn(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(fr, "next_worklist_line", lambda: "camp --n 1")
    monkeypatch.setattr(fr, "_run_campaign", lambda *a, **k: 1)   # always fails
    monkeypatch.setattr(fr, "_record", lambda *a, **k: None)      # never mark done
    rc = fr.main(["--dry-run", "--max-iters", "50"])
    assert rc == 1                                        # stopped LOUD, did not loop 50x


def test_loop_never_raises_out(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    def boom():
        raise RuntimeError("selection blew up")
    monkeypatch.setattr(fr, "next_worklist_line", boom)
    rc = fr.main(["--dry-run", "--max-iters", "50"])      # exception caught, fail-capped
    assert rc == 1                                        # stop-loud, NOT an uncaught raise


def test_effective_timeout_default_and_override():
    # INC-54: no @budget_h -> finite DEFAULT backstop (never unbounded); explicit wins up OR down.
    assert fr._effective_timeout_s(None) == fr.DEFAULT_MAX_WALL_H * 3600
    assert fr._effective_timeout_s(14) == 14 * 3600
    assert fr._effective_timeout_s(0.5) == 1800


class _FakeProc:
    """A child that never finishes -> wait() always times out (a hot-wedge)."""
    pid = 999999
    def poll(self):
        return None
    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired(cmd="x", timeout=timeout)


def test_wall_cap_kills_wedge_and_returns_intended_stop(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    killed = {"n": 0}
    monkeypatch.setattr(fr.subprocess, "Popen", lambda *a, **k: _FakeProc())
    monkeypatch.setattr(fr, "_kill_child_group", lambda p: killed.__setitem__("n", killed["n"] + 1))
    # no @budget_h -> the DEFAULT wall cap must fire, kill the group, and return 0 (not a fail loop)
    assert fr._run_campaign(["--campaign", "x", "--n", "179"], budget_h=None, dry=False) == 0
    assert killed["n"] == 1
    assert fr._CURRENT_CHILD is None                      # ref cleared in finally
    # explicit @budget_h path also kills + returns intended-stop
    assert fr._run_campaign(["--campaign", "x"], budget_h=2, dry=False) == 0
    assert killed["n"] == 2


def test_kill_child_group_reaps_detached_process(tmp_path):
    # real process in its OWN session (as _run_campaign spawns) must be reaped by group-kill.
    p = subprocess.Popen(["sleep", "60"], start_new_session=True)
    assert p.poll() is None
    fr._kill_child_group(p)
    time.sleep(0.2)
    assert p.poll() is not None                           # dead, not orphaned
    # idempotent + safe on an already-dead / None child
    fr._kill_child_group(p)
    fr._kill_child_group(None)


def test_dry_run_spawns_no_subprocess(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    def forbidden(*a, **k):
        raise AssertionError("dry-run must not spawn a subprocess")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    (tmp_path / "worklist.txt").write_text("ntru_wall_beta_bump --n 179\n")
    assert fr.main(["--dry-run"]) == 0                    # one pass, no spawn
    assert not fr.DONE_LOG.exists()                       # dry-run must NOT mark lines done


# ---------------------------------------------------------------------------
# Ultrareview PR #3 (2026-08-21): lock = shared _pidlock; refusal is a FAILURE
# exit so Restart=on-failure retries and `systemctl status` shows it, instead of
# exit-0 reading as an intended stop (never-idle floor silently dead).
# ---------------------------------------------------------------------------

def test_lock_reclaims_recycled_pid_running_related_tool(tmp_path, monkeypatch):
    from pathlib import Path
    lock = tmp_path / "forever_runner.lock"
    monkeypatch.setattr(fr, "LOCK", lock)
    lock.write_text(str(os.getpid()))                 # alive pid (this pytest)
    monkeypatch.setattr(Path, "read_bytes",
                        lambda self: b"tail\0-f\0scripts/forever_runner.py\0")
    assert fr.acquire_lock() is True                  # reclaimed, not blocked
    assert lock.read_text() == str(os.getpid())
    fr.release_lock()
    assert not lock.exists()


def test_lock_blocks_on_live_runner_and_main_exits_nonzero(tmp_path, monkeypatch):
    from pathlib import Path
    lock = tmp_path / "forever_runner.lock"
    monkeypatch.setattr(fr, "LOCK", lock)
    lock.write_text(str(os.getpid()))
    monkeypatch.setattr(Path, "read_bytes",
                        lambda self: b"/usr/bin/python3\0scripts/forever_runner.py\0")
    assert fr.acquire_lock() is False
    spawned = []
    monkeypatch.setattr(fr, "_install_signal_handlers", lambda: spawned.append("sig"))
    rc = fr.main([])                                  # not dry-run -> takes the lock path
    assert rc != 0                                    # on-failure restart, visible status
    assert spawned == []                              # refused before any work
    assert lock.read_text() == str(os.getpid())       # holder's lock untouched


def test_node_profile_flags_override_globals(tmp_path, monkeypatch):
    # Register originals with monkeypatch so main()'s global writes are undone.
    for name in ("WORKLIST", "FILLER_CAMPAIGN", "FILLER_CELLS",
                 "FILLER_WORKERS", "FILLER_TREE", "REPO"):
        monkeypatch.setattr(fr, name, getattr(fr, name))
    monkeypatch.setattr(fr, "REPO", tmp_path)
    (tmp_path / "wl.txt").write_text("")
    rc = fr.main(["--dry-run", "--max-iters", "1", "--worklist", "wl.txt",
                  "--filler-campaign", "ntru_g6k_backfill",
                  "--filler-cells", "167:3167,173:4073",
                  "--filler-workers", "6", "--filler-tree", "ntru_g6k"])
    assert rc == 0
    assert fr.WORKLIST == tmp_path / "wl.txt"             # relative -> repo-rooted
    assert fr.FILLER_CAMPAIGN == "ntru_g6k_backfill"
    assert fr.FILLER_CELLS == [(167, 3167), (173, 4073)]
    assert fr.FILLER_WORKERS == 6
    assert fr.FILLER_TREE == "ntru_g6k"


def test_filler_cells_bad_format_is_argparse_error(tmp_path, monkeypatch):
    import pytest
    for name in ("WORKLIST", "FILLER_CELLS", "REPO"):
        monkeypatch.setattr(fr, name, getattr(fr, name))
    with pytest.raises(SystemExit):
        fr.main(["--dry-run", "--max-iters", "1", "--filler-cells", "167x3167"])
