"""Parity tests for scripts/_seed_paths.py.

Every (campaign, params) combination must produce the same path that
migrate_seeds_to_new_layout.new_path_for() produces from an equivalent
manifest entry. That mirrors the one-shot migration, so the two code
paths stay in lock-step.
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import _seed_paths as sp  # noqa: E402
import migrate_seeds_to_new_layout as mig  # noqa: E402


def _entry(**kwargs):
    """Build a minimal manifest entry for the migrate side."""
    base = {
        "campaign": "main",
        "n": 50, "beta": 20, "seed": 1, "q": 97,
        "precision": 250, "max_tours": 70,
        "tags": [],
    }
    base.update(kwargs)
    return base


# ---------------- parity vs migrate.new_path_for() ------------------------


def test_main_matches_migrate():
    entry = _entry(n=100, beta=30, seed=7)
    assert sp.seed_path_for(
        "main", n=100, beta=30, seed=7,
    ) == mig.new_path_for(entry)


def test_main_cloud_matches_migrate():
    entry = _entry(n=100, beta=30, seed=7, tags=["cloud"])
    assert sp.seed_path_for(
        "main", n=100, beta=30, seed=7, cloud=True,
    ) == mig.new_path_for(entry)


def test_q3329_matches_migrate():
    entry = _entry(
        campaign="q3329", n=100, beta=30, seed=11,
        q=3329, precision=1000, max_tours=70,
    )
    assert sp.seed_path_for(
        "q3329", n=100, beta=30, seed=11,
        q=3329, precision=1000, max_tours=70,
    ) == mig.new_path_for(entry)


def test_q3329_fat_matches_migrate():
    entry = _entry(
        campaign="q3329", n=100, beta=30, seed=56,
        q=3329, precision=1000, max_tours=70, tags=["fat"],
    )
    assert sp.seed_path_for(
        "q3329", n=100, beta=30, seed=56,
        q=3329, precision=1000, max_tours=70, is_fat=True,
    ) == mig.new_path_for(entry)


def test_cliff500_matches_migrate():
    entry = _entry(
        campaign="cliff500", n=130, beta=40, seed=1,
        precision=500, max_tours=100,
    )
    assert sp.seed_path_for(
        "cliff500", n=130, beta=40, seed=1,
        precision=500, max_tours=100,
    ) == mig.new_path_for(entry)


def test_fplll_sensitivity_matches_migrate():
    entry = _entry(
        campaign="fplll_sensitivity",
        n=100, beta=30, seed=3,
        tags=["v5.4.3"], fplll_version="5.4.3",
    )
    assert sp.seed_path_for(
        "fplll_sensitivity", n=100, beta=30, seed=3,
        fplll_version="5.4.3",
    ) == mig.new_path_for(entry)


def test_tours3x_matches_migrate():
    entry = _entry(
        campaign="tours3x", n=60, beta=30, seed=45,
        max_tours=None, tags=["3x"],
    )
    assert sp.seed_path_for(
        "tours3x", n=60, beta=30, seed=45,
    ) == mig.new_path_for(entry)


def test_convergence_matches_migrate():
    entry = _entry(
        campaign="convergence",
        n=140, beta=30, seed=10, max_tours=500,
    )
    assert sp.seed_path_for(
        "convergence", n=140, beta=30, seed=10, max_tours=500,
    ) == mig.new_path_for(entry)


# ---------------- ntru_xarch (cross-architecture regeneration) -----------


def test_ntru_xarch_path_is_separate_tree():
    """ntru_xarch mirrors the ntru q/p{prec}_mt{mt} layout but routes to its
    own root so externally-regenerated seeds never collide with canonical
    ntru/ seeds."""
    p = sp.seed_path_for(
        "ntru_xarch", n=73, beta=20, seed=1,
        q=97, precision=250, max_tours=50,
    )
    assert p == os.path.join(
        "results", "seeds", "ntru_xarch", "q97", "p250_mt50",
        "n073_beta20", "seed0001.json",
    )
    # Must differ from the canonical ntru/ path for the same (n, β, seed).
    ntru_p = sp.seed_path_for(
        "ntru", n=73, beta=20, seed=1,
        q=97, precision=250, max_tours=50,
    )
    assert p != ntru_p
    assert "/ntru_xarch/" in p and "/ntru_xarch/" not in ntru_p


def test_ntru_xarch_requires_precision_and_max_tours():
    with pytest.raises(ValueError, match="precision"):
        sp.seed_path_for("ntru_xarch", n=73, beta=20, seed=1)
    with pytest.raises(ValueError, match="max_tours"):
        sp.seed_path_for(
            "ntru_xarch", n=73, beta=20, seed=1, precision=250,
        )


# ---------------- structural / error-handling checks ---------------------


def test_unknown_campaign_raises():
    with pytest.raises(ValueError, match="unknown campaign"):
        sp.seed_path_for("portfolio", n=1, beta=1, seed=1)


def test_q3329_requires_precision():
    with pytest.raises(ValueError, match="precision"):
        sp.seed_path_for("q3329", n=100, beta=30, seed=1)


def test_q3329_requires_max_tours():
    with pytest.raises(ValueError, match="max_tours"):
        sp.seed_path_for(
            "q3329", n=100, beta=30, seed=1,
            precision=1000,
        )


def test_fplll_sensitivity_requires_version():
    with pytest.raises(ValueError, match="fplll_version"):
        sp.seed_path_for(
            "fplll_sensitivity", n=100, beta=30, seed=1,
        )


def test_convergence_requires_max_tours():
    with pytest.raises(ValueError, match="max_tours"):
        sp.seed_path_for("convergence", n=140, beta=30, seed=1)


def test_seed_dir_for_is_the_dirname_of_seed_path_for():
    d = sp.seed_dir_for("main", n=100, beta=30)
    p = sp.seed_path_for("main", n=100, beta=30, seed=7)
    assert os.path.dirname(p) == d


def test_base_argument_prefixes_path():
    p = sp.seed_path_for("main", n=100, beta=30, seed=1, base="/repo")
    assert p.startswith("/repo/")
    assert p.endswith("results/seeds/main/q97/n100_beta30/seed0001.json")


def test_leaf_filename_format_zero_padded_seed():
    p = sp.seed_path_for("main", n=50, beta=20, seed=5)
    assert p.endswith("seed0005.json")


def test_main_cloud_only_suffix_when_campaign_is_main():
    """cloud=True on non-main campaign is a no-op (no _cloud suffix)."""
    p = sp.seed_path_for(
        "q3329", n=100, beta=30, seed=1,
        precision=1000, max_tours=70, cloud=True,
    )
    assert "_cloud" not in p
    assert p.endswith("seed0001.json")


def test_fat_suffix_composes_with_cloud():
    p = sp.seed_path_for(
        "main", n=50, beta=20, seed=1, cloud=True, is_fat=True,
    )
    assert p.endswith("seed0001_cloud_fat.json")
