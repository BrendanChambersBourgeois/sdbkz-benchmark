"""Tests for scripts/vecprobe_membership.py (rotation-span membership, exact).

Pins the verdict on hand-built vectors against a small real NTRU key:
  * a +/- cyclic rotation of s = (g, f) is in the Z-span and flagged as the secret;
  * an integer combination of rotations is in the Z-span but not the secret;
  * a q-vector (first basis row) is outside even the Q-span;
  * a Q-span-only vector (rational coefficient) is reported with its denominator;
  * the rref fallback (g(1) = f(1) = 0, rotations dependent) still finds members.
All I/O is against a tmp seed tree; no real cell is read.
"""
import importlib
import json
import os

import numpy as np

vm = importlib.import_module("vecprobe_membership")
build_ntru = importlib.import_module("generators").build_ntru

N, Q, SEED = 11, 3329, 7


def _key():
    _, f, g = build_ntru(N, Q, seed=SEED)
    return [int(c) for c in g], [int(c) for c in f]


def _rot2(s, i):
    n = len(s) // 2
    return vm._rotate(s[:n], n, i) + vm._rotate(s[n:], n, i)


def test_rotation_is_secret_and_in_zspan():
    g, f = _key()
    v = _rot2(g + f, 3)
    c = vm.classify(v, g, f, N)
    assert c["is_secret_rotation"] and c["in_qspan"] and c["in_zspan"] is True
    assert c["a_nnz"] == 1 and c["a_maxabs"] == 1 and c["cross_norm2"] == 0
    assert c["qspan_residual_frac"] == 0.0
    neg = [-x for x in v]
    assert vm.classify(neg, g, f, N)["is_secret_rotation"]


def test_integer_combination_in_zspan_not_secret():
    g, f = _key()
    s = g + f
    v = [3 * a + 2 * b - c for a, b, c in zip(_rot2(s, 0), _rot2(s, 3), _rot2(s, 5), strict=True)]
    c = vm.classify(v, g, f, N)
    assert not c["is_secret_rotation"]
    assert c["in_qspan"] and c["in_zspan"] is True
    assert c["a_nnz"] == 3 and c["a_sum"] == 4 and c["a_maxabs"] == 3
    assert c["a_norm2"] == 9 + 4 + 1


def test_q_vector_outside_qspan():
    g, f = _key()
    v = [Q] + [0] * (2 * N - 1)
    c = vm.classify(v, g, f, N)
    assert not c["in_qspan"] and c["in_zspan"] is False
    assert c["cross_norm2"] > 0 and c["qspan_residual_frac"] > 0
    assert c["a_nnz"] is None and c["a_denominator_lcm"] is None


def test_rational_coefficient_is_qspan_only():
    n = 3
    g, f = [2, 0, 0], [0, 2, 0]
    v = [1, 0, 0, 0, 1, 0]           # (1/2) * rotation 0
    c = vm.classify(v, g, f, n)
    assert c["in_qspan"] and c["in_zspan"] is False
    assert c["a_denominator_lcm"] == 2 and c["cross_norm2"] == 0
    assert not c["is_secret_rotation"]


def test_rref_fallback_when_neither_polynomial_is_a_unit():
    n = 5
    g, f = [1, -1, 0, 0, 0], [0, 1, -1, 0, 0]      # g(1) = f(1) = 0
    assert vm._cyc_inverse(g, n) is None and vm._cyc_inverse(f, n) is None
    s = g + f
    v = _rot2(s, 2)
    c = vm.classify(v, g, f, n)
    assert c["is_secret_rotation"] and c["in_zspan"] is True and c["kernel_dim"] == 1
    assert c["a_nnz"] == 1
    w = [Q] + [0] * (2 * n - 1)
    assert vm.classify(w, g, f, n)["in_qspan"] is False


def test_analyze_seed_end_to_end(tmp_path):
    g, f = _key()
    s = g + f
    comb = [a + b for a, b in zip(_rot2(s, 1), _rot2(s, 4), strict=True)]
    qrow = [Q] + [0] * (2 * N - 1)
    seed = {
        "n": N, "q": Q, "seed": SEED, "beta": 20, "status": "completed",
        "secret_norm2": sum(x * x for x in s),
        "short_vectors_sdbkz": [[sum(x * x for x in s), _rot2(s, 6)],
                                [sum(x * x for x in comb), comb],
                                [Q * Q, qrow]],
    }
    cell = tmp_path / "ntru_g6k_vecprobe" / f"q{Q}" / "p500_mt50" / f"n{N:03d}_beta20"
    cell.mkdir(parents=True)
    (cell / "seed0007.json").write_text(json.dumps(seed))
    out = tmp_path / "out.json"
    rc = vm.main(["--results-root", str(tmp_path), "--output", str(out)])
    assert rc == 0
    j = json.loads(out.read_text())
    assert j["summary"] == {
        "seeds": 1, "seeds_secret_mismatch": 0, "vectors": 3, "secret_rotations": 1,
        "non_exact_vectors": 2, "non_exact_in_zspan": 1, "non_exact_in_qspan_only": 0,
        "non_exact_outside_qspan": 1, "non_exact_undetermined": 0,
    }
    v = j["seeds"][0]["vectors"]
    assert [x["rank"] for x in v] == [0, 1, 2] and all(x["leg"] == "sdbkz" for x in v)
    assert v[1]["a_nnz"] == 2 and v[2]["in_qspan"] is False
    # byte-stable: a second run writes identical bytes
    first = out.read_bytes()
    vm.main(["--results-root", str(tmp_path), "--output", str(out)])
    assert out.read_bytes() == first


def test_analyze_seed_skips_seed_without_vectors(tmp_path):
    p = tmp_path / "seed0001.json"
    p.write_text(json.dumps({"n": N, "q": Q, "seed": SEED, "status": "completed"}))
    assert vm.analyze_seed(str(p)) is None


def test_secret_mismatch_refuses_to_classify(tmp_path):
    g, f = _key()
    s = g + f
    p = tmp_path / "seed0001.json"
    p.write_text(json.dumps({"n": N, "q": Q, "seed": SEED, "secret_norm2": 999999,
                             "short_vectors_bkz": [[sum(x * x for x in s), s]]}))
    rec = vm.analyze_seed(str(p))
    assert rec["secret_mismatch"] is True and rec["vectors"] == []


def test_regenerated_key_matches_bkz_core_convention():
    # s = (g, f) with g first, matching _bkz_core._secret_recovery.
    g, f = _key()
    assert len(g) == len(f) == N
    assert set(g) <= {-1, 0, 1} and set(f) <= {-1, 0, 1}
    assert isinstance(np.asarray(g), np.ndarray)
    assert os.path.basename(vm.DEFAULT_OUTPUT) == "vecprobe_membership.json"
