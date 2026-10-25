"""check_bases_exact: the all-integer verdicts agree with fpylll's
float GSO on small bases, and each defect class is caught."""
import json
import os
import sys

import numpy as np
from fpylll import GSO, LLL, IntegerMatrix

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import check_bases_exact as cbe  # noqa: E402


def _np(B):
    A = np.zeros((B.nrows, B.ncols), dtype=np.int64)
    B.to_matrix(A)
    return A


def _qary(seed=3):
    from fpylll import FPLLL
    FPLLL.set_random_seed(seed)
    return IntegerMatrix.random(30, "qary", k=15, bits=10)


def test_lll_reduced_basis_passes_and_margins_match_float_gso():
    L = _qary()
    B = IntegerMatrix(L)
    LLL.reduction(B)
    dn_ref = cbe.integral_gso(_np(L))[0][-1]
    r = cbe.check_basis(_np(B), dn_ref)
    assert r["full_rank"] and r["det_eq"] and r["size_ok"] and r["lovasz_ok"]
    M = GSO.Mat(B)
    M.update_gso()
    n = B.nrows
    mu = max(abs(M.get_mu(i, j)) for i in range(n) for j in range(i))
    lov = min((M.get_r(k, k) + M.get_mu(k, k - 1) ** 2 * M.get_r(k - 1, k - 1))
              / M.get_r(k - 1, k - 1) for k in range(1, n))
    assert abs(r["max_mu"] - mu) < 1e-9
    assert abs(r["lovasz_min"] - lov) < 1e-9


def test_unreduced_qary_basis_fails_lovasz_or_size():
    L = _np(_qary())
    dn_ref = cbe.integral_gso(L)[0][-1]
    r = cbe.check_basis(L, dn_ref)
    assert r["full_rank"] and r["det_eq"]
    assert not (r["size_ok"] and r["lovasz_ok"])


def test_scaled_row_breaks_det_and_duplicate_row_breaks_rank():
    B = IntegerMatrix(_qary())
    LLL.reduction(B)
    A = _np(B)
    dn_ref = cbe.integral_gso(A)[0][-1]
    S = A.copy()
    S[5] *= 2
    assert cbe.check_basis(S, dn_ref)["det_eq"] is False
    D = A.copy()
    D[7] = D[3]
    r = cbe.check_basis(D, dn_ref)
    assert r["full_rank"] is False and r["first_nonpos_row"] == 7


def test_check_file_reads_the_q3329_verify_layout(tmp_path):
    L = _qary()
    B = IntegerMatrix(L)
    LLL.reduction(B)
    A = _np(B)
    p = tmp_path / "seed0001.npz"
    meta = {"n": 15, "beta": 10, "seed": 1}
    np.savez_compressed(p, meta=np.array(json.dumps(meta)), L=_np(L),
                        init=A[None], bkz=np.stack([A, A]), sdbkz=A[None])
    recs, summ = cbe.check_file(str(p))
    assert [(r["leg"], r["tour"]) for r in recs] == [
        ("init", 0), ("bkz", 1), ("bkz", 2), ("sdbkz", 1)]
    assert summ == {"file_done": str(p), "bases": 4, "failing": 0, "failing_legs": []}
    recs, summ = cbe.check_file(str(p), final_only=True)
    assert [(r["leg"], r["tour"]) for r in recs] == [("bkz", 2), ("sdbkz", 1)]
    assert summ["bases"] == 2
