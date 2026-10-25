"""g6k container re-exec + full-failure rc.

  1. a g6k campaign dispatched where the g6k module is missing re-execs the
     exact invocation inside G6K_IMAGE;
  2. a run whose every attempted seed failed returns rc=1.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import run_campaign as rc  # noqa: E402


# ------------------------------------------------------------- full-failure rc
def test_all_attempted_failed_is_failure():
    assert rc._ntru_full_failure(total=20, skipped=0, written=0)


def test_all_skip_stays_success():
    # Filler steady state: fully-populated cell re-dispatched every minute.
    assert not rc._ntru_full_failure(total=80, skipped=80, written=0)


def test_partial_write_stays_success():
    # Wave semantics: surviving seeds count even when siblings errored.
    assert not rc._ntru_full_failure(total=20, skipped=0, written=3)


def test_skips_plus_failures_no_writes_is_failure():
    # 5 pre-existing seeds skipped, remaining 15 all errored -> still a failure.
    assert rc._ntru_full_failure(total=20, skipped=5, written=0)


def test_zero_tasks_stays_success():
    assert not rc._ntru_full_failure(total=0, skipped=0, written=0)


# --------------------------------------------------------- container re-exec
def test_container_argv_shape():
    argv = rc._g6k_container_argv(
        ["--campaign", "ntru_wall_beta_bump", "--n", "181", "--q", "3733"])
    assert argv[:4] == ["docker", "run", "--rm", "--init"]
    assert rc.G6K_IMAGE in argv
    # seed files must land owned by the invoking user, not root
    assert f"{os.getuid()}:{os.getgid()}" == argv[argv.index("--user") + 1]
    # recursion guard travels into the container
    assert f"{rc._IN_CONTAINER_ENV}=1" in argv
    # desktop-starvation fix: containerd children never see the Nice=19 drop-in
    i = argv.index(rc.G6K_IMAGE)
    assert argv[i + 1:i + 4] == ["nice", "-n", "19"]
    # the original invocation is forwarded verbatim after the interpreter
    assert argv[-7:] == ["scripts/run_campaign.py", "--campaign",
                         "ntru_wall_beta_bump", "--n", "181", "--q", "3733"]
    # repo bind-mounted at the fixed in-container workdir
    assert f"{rc.REPO_ROOT}:/experiment" in argv
    assert argv[argv.index("-w") + 1] == "/experiment"


def test_g6k_available_matches_find_spec():
    import importlib.util
    assert rc._g6k_available() == (importlib.util.find_spec("g6k") is not None)


# -- §8 local rerun arms: q3329_* routing, --image re-exec ------

def test_select_runner_routes_q3329_rerun_arms():
    assert rc._select_runner("q3329_kahan") == "q3329_verify"
    assert rc._select_runner("q3329_control") == "q3329_verify"


def test_container_argv_name_prefix():
    default = rc._g6k_container_argv(["--campaign", "x"])
    assert default[default.index("--name") + 1].startswith("runcamp-g6k-")
    fplll = rc._g6k_container_argv(
        ["--campaign", "x"], image="sdbkz-fplll-patched:kahan-v3",
        name_prefix="runcamp-fplll")
    assert fplll[fplll.index("--name") + 1].startswith("runcamp-fplll-")
    assert "sdbkz-fplll-patched:kahan-v3" in fplll
    assert rc.G6K_IMAGE not in fplll


def test_q3329_rerun_arms_load_with_own_trees():
    for name in ("q3329_kahan", "q3329_control"):
        c = rc.load_campaign(name)
        assert c.seed_tag == name
        assert (c.q, c.precision) == (3329, 1000)
        assert (tuple(c.n_grid), tuple(c.beta_grid)) == ((100,), (30,))
        assert c.tours_by_beta[30] == 70
        assert c.num_seeds == 100
        assert c.backend == "fplll"


def test_dispatch_q3329_verify_forwards_workers_and_seed_tag(capsys):
    c = rc.load_campaign("q3329_kahan")
    rc._dispatch_q3329_verify(c, 100, 30, start=1, end=100, seeds=100,
                              workers=20, dry_run=True)
    out = capsys.readouterr().out
    assert "--seed-tag q3329_kahan" in out
    assert "--workers 20" in out
    assert "--max-tours 70" in out
    assert "--precision 1000" in out
    # canonical q3329 keeps the default tree: no --seed-tag on its argv
    rc._dispatch_q3329_verify(rc.load_campaign("q3329"), 100, 30, start=1,
                              end=100, seeds=100, workers=1, dry_run=True)
    assert "--seed-tag" not in capsys.readouterr().out


def test_dispatch_q3329_verify_forwards_seed_window(capsys):
    # 2026-10-24: --start 51 --end 100 became "--seeds 50" alone, so the
    # runner ran seeds 1-50 (all on disk) and did nothing.
    rc._dispatch_q3329_verify(rc.load_campaign("q3329_mpfr"), 80, 30, start=51,
                              end=100, seeds=50, workers=1, dry_run=True)
    assert "--seeds 50 --start 51 " in capsys.readouterr().out


def test_dispatch_q3329_verify_forwards_store_per_tour_and_metric(capsys):
    # both knobs were dropped for q3329 campaigns.
    rc._dispatch_q3329_verify(rc.load_campaign("q3329_kahan"), 100, 30,
                              start=1, end=100, seeds=100, workers=1,
                              dry_run=True)
    out = capsys.readouterr().out
    assert "--store-per-tour" in out
    assert "--metric-float-type" not in out  # double stays implicit
    assert "--store-bases" not in out
    c = rc.load_campaign("q3329_mpfr")
    assert (c.seed_tag, c.metric_float_type) == ("q3329_mpfr", "mpfr")
    rc._dispatch_q3329_verify(c, 100, 30, start=1, end=100, seeds=100,
                              workers=20, dry_run=True)
    out = capsys.readouterr().out
    assert "--metric-float-type mpfr" in out
    assert "--seed-tag q3329_mpfr" in out
    assert "--store-bases" in out  # off unless a campaign asks
    rc._dispatch_q3329_verify(rc.load_campaign("main"), 100, 30, start=1,
                              end=100, seeds=100, workers=1, dry_run=True)
    assert "--store-per-tour" not in capsys.readouterr().out


# -- reject tree: refuse a siever without the overflow guard -------------

@pytest.mark.parametrize("campaign", ["ntru_wall_beta_bump_reject", "ntru_g6k_vecprobe_reject"])
def test_reject_tree_refuses_siever_without_guard(monkeypatch, capsys, campaign):
    # In a container the image key is never checked; the siever must prove it.
    monkeypatch.setenv("PIPELINE_LOG_TAG", "test")  # --dry-run rewrites it
    monkeypatch.setattr(rc, "_g6k_available", lambda: True)
    monkeypatch.setattr(rc, "_siever_has_reject_guard", lambda: False)
    monkeypatch.setattr(sys, "argv", ["run_campaign.py", "--campaign",
                                      campaign, "--dry-run"])
    assert rc.main() == 2
    assert "reject-on-overflow guard" in capsys.readouterr().err


def test_siever_guard_reads_loaded_siever_so(tmp_path, monkeypatch):
    import types
    so = tmp_path / "siever.so"
    pkg, mod = types.ModuleType("g6k"), types.ModuleType("g6k.siever")
    mod.__file__, pkg.siever = str(so), mod
    monkeypatch.setitem(sys.modules, "g6k", pkg)
    monkeypatch.setitem(sys.modules, "g6k.siever", mod)
    so.write_bytes(b"\0g6k reduce_in_db: " + rc._REJECT_MARKER + b" #%d\0")
    assert rc._siever_has_reject_guard()
    so.write_bytes(b"\0tolerant build\0")
    assert not rc._siever_has_reject_guard()
