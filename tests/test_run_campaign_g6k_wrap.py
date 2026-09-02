"""g6k container re-exec + full-failure rc (2026-08-28 incident).

All 12 queued beta=50 worklist lines dispatched host-side, every seed died in
seconds with "ModuleNotFoundError: No module named 'g6k'", run_campaign
returned rc=0 ("NTRU run OK: 0 seeds written / 20 tasks"), and forever_runner
archived the whole 7.2-day ladder as done in ~12 minutes. Two guards now:

  1. a g6k campaign dispatched where the g6k module is missing re-execs the
     exact invocation inside G6K_IMAGE (scripts/run_campaign.py owns campaign
     config, so the wrap lives there, not in forever_runner);
  2. a run whose every ATTEMPTED seed failed returns rc=1, so the runner's
     FAILED_LOG + consecutive-failure stop-loud path engage.
"""
import os
import sys

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


# -- §8 local rerun arms (2026-09-02): q3329_* routing, --image re-exec ------

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
