"""forever_runner — the reconciled minimal never-idle loop (B2 review).

Tests target exactly the review-flagged failure modes: stop-LOUD after repeated
failure (not churn), never raise out of the loop, no busy-spin path, filler
targets the least-sampled ntru_b2 cell, and the worklist is consumed via a
done-log (never rewritten, comments/blanks skipped, completed lines not retried).
"""
import os
import sys

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


def test_dry_run_spawns_no_subprocess(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    import subprocess
    def forbidden(*a, **k):
        raise AssertionError("dry-run must not spawn a subprocess")
    monkeypatch.setattr(subprocess, "run", forbidden)
    (tmp_path / "worklist.txt").write_text("ntru_wall_beta_bump --n 179\n")
    assert fr.main(["--dry-run"]) == 0                    # one pass, no spawn
    assert not fr.DONE_LOG.exists()                       # dry-run must NOT mark lines done
