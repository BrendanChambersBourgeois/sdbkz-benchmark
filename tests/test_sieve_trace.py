"""Sieve-trace plumbing: opt-in sieve trace, tour_cb, NTRU seed range.

Host-side (no g6k). The g6k reduction itself is covered in the g6k image by
tests/test_sieve_trace_g6k.py.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import _seed_paths as sp  # noqa: E402
from _bkz_core import run_single  # noqa: E402
from _config import ConfigError, _to_campaign, load_campaign  # noqa: E402
from _engine_backends import _SieveTimer, make_backend  # noqa: E402
from generators import build_lwe_kannan, kannan_m  # noqa: E402


class _FakeSiever:
    def __init__(self):
        self.n = 0
        self.db = 0

    def __len__(self):
        return self.db


def test_sieve_timer_aggregates_sieves_and_pumps():
    g = _FakeSiever()
    t = _SieveTimer(g)
    for kappa in range(3):
        t.enter(("pump", "beta:60 f:16"))
        for dim, alg in ((30, "gauss"), (31, "gauss"), (44, "hk3")):
            g.n, g.db = dim, 10 * dim
            t.enter(alg)
            t.exit()
        t.exit()
    s = t.summary()
    assert s["pumps"] == 3
    assert s["by_alg"]["gauss"][0] == 6 and s["by_alg"]["hk3"][0] == 3
    assert s["by_dim"]["44"][0] == 3
    assert s["max_db"] == 440
    assert [p[0] for p in s["slowest_pumps"]] and len(s["slowest_pumps"]) == 3
    t.reset()
    assert t.summary()["pumps"] == 0


def test_sieve_trace_is_g6k_only():
    with pytest.raises(ValueError):
        make_backend("fplll", B_init=None, beta=10, variant="bkz", seed=1,
                     precision=100, sieve_trace=True)
    base = load_campaign("ntru_n127_patched")
    merged = {"q": base.q, "precision": base.precision, "beta_grid": [20],
              "n_grid": [127], "tours_by_beta": {"20": 50}, "num_seeds": 4,
              "generator": "ntru", "sieve_trace": True}
    with pytest.raises(ConfigError):
        _to_campaign("x", merged)


def test_q09_campaign_shape():
    c = load_campaign("ntru_q09_diag")
    assert (c.backend, c.seed_tag, c.sieve_trace, c.store_per_tour,
            c.seed_wall_s) == ("g6k", "ntru_g6k_diag", True, True, 432000)
    # Cell pinned so a bare dispatch cannot fan out over the parent's grid.
    assert (c.n_grid, c.q, c.beta_grid, c.image) == \
        ((185,), 3907, (60,), "sdbkz-g6k:dim384-inc63")
    assert load_campaign("ntru_n127_kahan_v3").image == \
        "sdbkz-fplll-patched:kahan-v3"
    assert load_campaign("ntru_wall_beta_bump").sieve_trace is False


def test_diag_tree_is_its_own_root():
    d = sp.seed_dir_for("ntru_g6k_diag", 185, 60, q=3907, precision=500,
                        max_tours=50)
    assert d == os.path.join("results", "seeds", "ntru_g6k_diag", "q3907",
                             "p500_mt50", "n185_beta60")


def _tiny(**kw):
    L, _, _ = build_lwe_kannan(20, kannan_m(20), 97, seed=1)
    return run_single(L=L, n=20, active_block_start=kannan_m(20),
                      active_block_end=20 + kannan_m(20) + 1, beta=10, seed=1,
                      q=97, precision=100, max_tours=4, log_clamp_fn=None,
                      **kw)


_VOLATILE = {"timestamp", "bkz_time", "sdbkz_time"}


def test_tour_cb_called_per_tour_and_never_changes_science():
    calls = []
    plain = _tiny()
    traced = _tiny(tour_cb=lambda *a: calls.append(a))
    assert {k: v for k, v in plain.items() if k not in _VOLATILE} == \
        {k: v for k, v in traced.items() if k not in _VOLATILE}
    per_variant = {v: [c[1] for c in calls if c[0] == v]
                   for v in ("bkz", "sdbkz")}
    assert per_variant["bkz"] == list(range(1, plain["bkz_tours_run"] + 1))
    assert per_variant["sdbkz"] == list(range(1, plain["sdbkz_tours_run"] + 1))
    assert [c[4] for c in calls if c[0] == "bkz"] == plain["bkz_dln_per_tour"]
    assert all(c[5] is None for c in calls)  # fplll engine has no sieve stats


def test_broken_tour_cb_is_swallowed():
    def boom(*a):
        raise RuntimeError("side channel only")
    assert _tiny(tour_cb=boom)["status"] == "completed"


def _dry(*args, campaign="ntru_n127_patched"):
    out = subprocess.run(
        [sys.executable, "scripts/run_campaign.py", "--campaign",
         campaign, "--q", "971", "--dry-run", *args],
        cwd=REPO_ROOT, capture_output=True, text=True)
    return out.returncode, [l for l in out.stdout.splitlines()
                            if l.startswith("[dry-run]")], out.stderr


def test_ntru_seed_range():
    rc, lines, _ = _dry("--start", "3", "--end", "4")
    assert rc == 0 and [l.split("seed=")[1].split()[0] for l in lines] == \
        ["3", "4"]
    rc, lines, _ = _dry()
    assert rc == 0 and len(lines) == 4
    rc, _, err = _dry("--start", "5", "--end", "4")
    assert rc == 2 and "bad seed range" in err


def test_campaign_image_refuses_other_engine():
    # The kahan-v3 tree name is its only provenance: a run on another
    # image must stop before anything is dispatched.
    rc, lines, err = _dry("--image", "sdbkz-fplll-patched:reorder-control",
                          campaign="ntru_n127_kahan_v3")
    assert rc == 2 and not lines and "runs only in" in err
