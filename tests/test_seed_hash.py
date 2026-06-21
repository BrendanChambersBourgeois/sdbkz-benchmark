"""Tests for scripts/_seed_hash.py — the centralised science-field hash.

Guards that the digest depends only on deterministic science fields and ignores
the environment-dependent ones, and that the dict and file-path entry points
agree. Byte-compatibility with the pre-centralisation validate_seeds code is
checked separately against the committed REFERENCE_HASHES in test_validate_seeds
/ the --sha-check CI gate.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import _seed_hash as sh  # noqa: E402

_SEED = {
    "n": 73, "beta": 20, "seed": 1, "q": 97, "precision": 250, "max_tours": 50,
    "advantage": 8.643717277579753,
    "bkz_final_dln": 28.4, "sdbkz_final_dln": 19.756,
    "gs_lognorms_bkz": [1.0, 2.0, 3.0],
    # environment-dependent — must NOT affect the hash:
    "bkz_time": 120.147, "sdbkz_time": 259.51,
    "timestamp": "2026-06-03T07:35:16.985455+00:00", "status": "completed",
}


def test_exclude_set_is_the_four_env_fields():
    assert sh.SCIENCE_EXCLUDE == {"bkz_time", "sdbkz_time", "timestamp", "status"}


def test_hash_is_deterministic():
    assert sh.science_hash(dict(_SEED)) == sh.science_hash(dict(_SEED))


def test_excluded_fields_do_not_change_hash():
    base = sh.science_hash(_SEED)
    for k, v in [("bkz_time", 0.0), ("sdbkz_time", 0.0),
                 ("timestamp", "1999-01-01T00:00:00+00:00"),
                 ("status", "whatever")]:
        d = dict(_SEED)
        d[k] = v
        assert sh.science_hash(d) == base, f"{k} leaked into the hash"


def test_science_field_change_changes_hash():
    d = dict(_SEED)
    d["advantage"] = _SEED["advantage"] + 1e-9
    assert sh.science_hash(d) != sh.science_hash(_SEED)


def test_dict_and_path_agree(tmp_path):
    p = tmp_path / "seed0001.json"
    p.write_text(json.dumps(_SEED))
    assert sh.science_hash(str(p)) == sh.science_hash(_SEED)


def test_key_order_independent():
    reordered = {k: _SEED[k] for k in reversed(list(_SEED))}
    assert sh.science_hash(reordered) == sh.science_hash(_SEED)
