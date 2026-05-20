"""Tests for scripts/_config.py — campaign TOML loader.

Two layers of coverage:

  1. Real-file: load the committed `config/sweep.toml` and assert the
     campaign names + key invariants survive a round-trip. Catches
     accidental schema drift in the data file.

  2. Synthetic: inline TOML strings written to tmp_path exercise every
     validation branch (missing required keys, unknown keys, inheritance
     cycles, bad types, version mismatch, tours_by_beta coverage of
     beta_grid, etc.). Synthetic fixtures avoid any dependency on the
     committed data file's specific contents.
"""
from __future__ import annotations

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import _config  # noqa: E402


# ---------------------------------------------------------------------------
# Real-file round-trip — protects the committed config/sweep.toml
# ---------------------------------------------------------------------------

def test_real_file_loads_all_campaigns():
    campaigns = _config.load_all_campaigns()
    assert "main" in campaigns
    assert "q3329" in campaigns
    assert "cliff500" in campaigns
    assert "convergence_beta40_mt1000" in campaigns


def test_real_main_campaign_matches_sweep_parallel_constants():
    main = _config.load_campaign("main")
    assert main.q == 97
    assert main.precision == 250
    assert main.beta_grid == (20, 30, 40)
    assert main.n_grid == tuple(range(50, 151, 10))
    assert main.tours_by_beta == {20: 50, 30: 70, 40: 100}
    assert main.num_seeds == 100
    assert main.store_per_tour is False


def test_real_q3329_campaign_matches_q3329_verify_constants():
    q = _config.load_campaign("q3329")
    assert q.q == 3329
    assert q.precision == 1000
    assert q.beta_grid == (30,)
    assert 100 in q.n_grid


def test_real_cliff500_inherits_q97_then_overrides_precision():
    cliff = _config.load_campaign("cliff500")
    assert cliff.q == 97
    assert cliff.precision == 500
    assert cliff.beta_grid == (40,)
    assert cliff.n_grid == (130,)


def test_real_convergence_beta40_bracket_has_eight_dims():
    bracket = _config.load_campaign("convergence_beta40_mt1000")
    assert bracket.beta_grid == (40,)
    assert bracket.n_grid == (110, 120, 122, 125, 130, 140, 150, 160)
    assert bracket.tours_by_beta[40] == 1000


# ---------------------------------------------------------------------------
# Synthetic — exercises every validation branch
# ---------------------------------------------------------------------------

def _write(tmp_path, body):
    p = tmp_path / "sweep.toml"
    p.write_text(body)
    return str(p)


MINIMAL = """
config_version = 1
[default]
q = 97
precision = 250
num_seeds = 5
store_per_tour = false
[campaigns.toy]
beta_grid = [10]
n_grid = [20]
tours_by_beta = { "10" = 3 }
"""


def test_minimal_synthetic_loads(tmp_path):
    c = _config.load_campaign("toy", path=_write(tmp_path, MINIMAL))
    assert c.q == 97
    assert c.precision == 250
    assert c.num_seeds == 5
    assert c.beta_grid == (10,)


def test_missing_file_raises(tmp_path):
    with pytest.raises(_config.ConfigError, match="not found"):
        _config.load_all_campaigns(path=str(tmp_path / "missing.toml"))


def test_bad_toml_syntax_raises(tmp_path):
    p = _write(tmp_path, "this is not = valid toml [[[")
    with pytest.raises(_config.ConfigError, match="TOML parse error"):
        _config.load_all_campaigns(path=p)


def test_unknown_root_key_rejected(tmp_path):
    # TOML scopes keys to the nearest preceding [table]; placing the
    # strange key before any [section] header keeps it at the true
    # root so the test exercises the root-validator branch.
    body = "strange_global = 1\n" + MINIMAL
    with pytest.raises(_config.ConfigError, match="unknown root keys"):
        _config.load_all_campaigns(path=_write(tmp_path, body))


def test_unknown_campaign_key_rejected(tmp_path):
    body = MINIMAL.replace(
        "[campaigns.toy]",
        "[campaigns.toy]\nmade_up_field = 7",
    )
    with pytest.raises(_config.ConfigError, match="unknown keys"):
        _config.load_all_campaigns(path=_write(tmp_path, body))


def test_missing_required_field_rejected(tmp_path):
    # Drop tours_by_beta from the toy campaign — but supply a default
    # block that also lacks it so the merge can't recover. The minimal
    # body's `tours_by_beta = { "10" = 3 }` is the line to delete.
    body = MINIMAL.replace('tours_by_beta = { "10" = 3 }\n', "")
    with pytest.raises(_config.ConfigError, match="missing required keys"):
        _config.load_all_campaigns(path=_write(tmp_path, body))


def test_version_mismatch_rejected(tmp_path):
    body = MINIMAL.replace("config_version = 1", "config_version = 2")
    with pytest.raises(_config.ConfigError, match="unsupported config_version"):
        _config.load_all_campaigns(path=_write(tmp_path, body))


def test_unknown_campaign_name_rejected(tmp_path):
    p = _write(tmp_path, MINIMAL)
    with pytest.raises(_config.ConfigError, match="unknown campaign"):
        _config.load_campaign("does_not_exist", path=p)


def test_inheritance_resolves(tmp_path):
    body = """
config_version = 1
[default]
q = 97
precision = 250
num_seeds = 5
store_per_tour = false
[campaigns.base]
beta_grid = [10]
n_grid = [20, 30]
tours_by_beta = { "10" = 4 }
[campaigns.child]
inherits = "base"
n_grid = [50]
"""
    child = _config.load_campaign("child", path=_write(tmp_path, body))
    # Inherited from base / default:
    assert child.beta_grid == (10,)
    assert child.q == 97
    assert child.tours_by_beta == {10: 4}
    # Overridden by child:
    assert child.n_grid == (50,)


def test_inheritance_cycle_rejected(tmp_path):
    body = """
config_version = 1
[default]
q = 97
precision = 250
num_seeds = 5
store_per_tour = false
[campaigns.a]
inherits = "b"
beta_grid = [10]
n_grid = [20]
tours_by_beta = { "10" = 3 }
[campaigns.b]
inherits = "a"
beta_grid = [10]
n_grid = [20]
tours_by_beta = { "10" = 3 }
"""
    with pytest.raises(_config.ConfigError, match="cycle"):
        _config.load_all_campaigns(path=_write(tmp_path, body))


def test_tours_by_beta_must_cover_beta_grid(tmp_path):
    body = MINIMAL.replace(
        "beta_grid = [10]",
        "beta_grid = [10, 20]",
    )
    with pytest.raises(_config.ConfigError, match="no entry in tours_by_beta"):
        _config.load_all_campaigns(path=_write(tmp_path, body))


def test_negative_q_rejected(tmp_path):
    body = MINIMAL.replace("q = 97", "q = -1")
    with pytest.raises(_config.ConfigError, match="q must be positive"):
        _config.load_all_campaigns(path=_write(tmp_path, body))


def test_negative_precision_rejected(tmp_path):
    body = MINIMAL.replace("precision = 250", "precision = 0")
    with pytest.raises(_config.ConfigError, match="precision must be positive"):
        _config.load_all_campaigns(path=_write(tmp_path, body))


def test_empty_n_grid_rejected(tmp_path):
    body = MINIMAL.replace("n_grid = [20]", "n_grid = []")
    with pytest.raises(_config.ConfigError, match="n_grid must be non-empty"):
        _config.load_all_campaigns(path=_write(tmp_path, body))


def test_negative_tours_rejected(tmp_path):
    body = MINIMAL.replace('tours_by_beta = { "10" = 3 }',
                           'tours_by_beta = { "10" = 0 }')
    with pytest.raises(_config.ConfigError, match="must be positive"):
        _config.load_all_campaigns(path=_write(tmp_path, body))


def test_default_block_must_be_table(tmp_path):
    body = """
config_version = 1
default = "not a table"
[campaigns.toy]
beta_grid = [10]
n_grid = [20]
tours_by_beta = { "10" = 3 }
"""
    with pytest.raises(_config.ConfigError, match=r"\[default\] must be a table"):
        _config.load_all_campaigns(path=_write(tmp_path, body))


def test_load_all_returns_every_campaign(tmp_path):
    p = _write(tmp_path, MINIMAL)
    out = _config.load_all_campaigns(path=p)
    assert set(out.keys()) == {"toy"}
    assert out["toy"].name == "toy"
