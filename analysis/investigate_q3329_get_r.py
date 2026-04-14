#!/usr/bin/env python3
"""Investigate what fpylll's get_r returns when q3329_verify clamps it.

Reproduces the known-degenerate cloud seed 1 (n=100, β=30, q=3329,
1000-bit MPFR), runs BKZ tour by tour, and after each tour scans all
positions for `M.get_r(i, i) <= 0`. When the first non-positive value
is found, captures the raw value and reports whether it is:

  - **Negative**  → numerical underflow / cancellation in fpylll's
                    MPFR-based GSO update; squared norms are
                    mathematically non-negative, so a negative value
                    is a numerical bug
  - **Exactly 0** → a real geometric collapse: the Gram-Schmidt
                    vector is genuinely zero, meaning the lattice
                    has effectively linearly dependent vectors at
                    that position
  - **NaN**       → would not actually trigger our `<= 0` check
                    because NaN comparisons return False, but worth
                    checking explicitly

This answers the question raised by q3329_degeneracy_check.py: the
−345.39 floor is set by our defensive clamp at q3329_verify.py:88
(`r_val = 1e-300` when get_r returns ≤ 0). What does get_r ACTUALLY
return when the clamp fires? That distinguishes a real geometric
phenomenon from an fpylll numerical bug.

From the seed-1 data: initial post-LLL state is clean (min gs_lognorm
≈ −0.0004). Only position 288 in the final state has a bad value. So
the degeneracy appears DURING BKZ, not at LLL setup.

Usage:
    nohup python3 analysis/investigate_q3329_get_r.py \\
        > logs/investigate_q3329_get_r.log 2>&1 &

Per-tour cost at n=100 β=30 1000-bit MPFR is ~8-12 minutes. The
script stops at the first tour where any position hits `r_val ≤ 0`,
so total wall time depends on which tour first triggers the issue —
could be minutes (if early) or hours (if late).
"""
import os
import sys
import json
import time
import datetime

# Resolve `from analysis...` and `import q3329_verify` from this script
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

# q3329_verify mocks argv at import time. Set it up for n=100, β=30,
# 1000-bit precision (matching cloud seed 1's configuration).
_argv_save = sys.argv
sys.argv = [
    "q3329_verify.py",
    "--n", "100",
    "--beta", "30",
    "--seeds", "1",
    "--precision", "1000",
]
import q3329_verify  # noqa: E402
sys.argv = _argv_save

from fpylll import IntegerMatrix, LLL, BKZ, FPLLL, GSO  # noqa: E402


# ── Config ──────────────────────────────────────────────────────────────────

SEED = 1
N = 100
BETA = 30
Q = 3329
PRECISION = 1000
MAX_TOURS_TO_TRY = 70

OUT_PATH = os.path.join(REPO, "results", "q3329_get_r_investigation.json")


# ── Helpers ─────────────────────────────────────────────────────────────────

def scan_get_r(M, dim, m, label=""):
    """Call get_r(i, i) for every position; flag any non-positive values.

    Returns a dict with the scan result. The active block is [m, dim);
    positions outside that range are the q-vectors region of the
    Kannan embedding (always positive, present for context only).
    """
    bad = []
    all_r = []
    for i in range(dim):
        r_val = M.get_r(i, i)
        # Convert to float for JSON; track original behaviour
        try:
            r_float = float(r_val)
        except (ValueError, OverflowError):
            r_float = None
        all_r.append(r_float)
        if r_val <= 0:
            bad.append({
                "position": i,
                "in_active_block": i >= m,
                "active_block_index": (i - m) if i >= m else None,
                "raw_repr": repr(r_val),
                "raw_str": str(r_val),
                "as_float": r_float,
                "is_negative": bool(r_val < 0),
                "is_zero": bool(r_val == 0),
                "is_nan": bool(r_val != r_val),
            })

    valid_r = [r for r in all_r if r is not None and r > 0]
    return {
        "label": label,
        "found": len(bad) > 0,
        "n_bad": len(bad),
        "bad_positions": bad,
        "min_positive_r": min(valid_r) if valid_r else None,
        "max_r": max(valid_r) if valid_r else None,
        "n_positions_scanned": dim,
    }


def save(payload, status, path=OUT_PATH):
    payload["status"] = status
    payload["generated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    payload["config"] = {
        "seed": SEED, "n": N, "beta": BETA, "q": Q,
        "precision": PRECISION, "max_tours": MAX_TOURS_TO_TRY,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"  Saved: {path}")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print(f"Investigating raw get_r for seed {SEED} "
          f"(n={N}, β={BETA}, q={Q}, {PRECISION}-bit MPFR)")
    print("=" * 72)
    print(f"  Q={q3329_verify.Q}  PRECISION={q3329_verify.PRECISION}  "
          f"MAX_TOURS={q3329_verify.MAX_TOURS}")
    print()

    FPLLL.set_precision(PRECISION)
    FPLLL.set_random_seed(SEED)

    m = N * 2
    dim = m + N + 1
    print(f"Building LWE-Kannan lattice: n={N}, m={m}, dim={dim}, q={Q}")
    L, _, _ = q3329_verify.build_lwe_kannan(N, m, Q, seed=SEED)

    print("LLL reducing...")
    t_lll = time.time()
    B = IntegerMatrix.from_matrix(L)
    LLL.reduction(B)
    print(f"  LLL took {time.time() - t_lll:.1f}s")

    M = GSO.Mat(B)
    M.update_gso()
    lll_scan = scan_get_r(M, dim, m, label="post-LLL")
    print(f"  post-LLL scan: n_bad={lll_scan['n_bad']}, "
          f"min_positive_r={lll_scan['min_positive_r']:.6e}, "
          f"max_r={lll_scan['max_r']:.6e}")

    if lll_scan["found"]:
        print()
        print("!! BAD VALUES ALREADY PRESENT AFTER LLL — degeneracy is in "
              "the input lattice or the LLL/GSO setup, not BKZ.")
        save({"lll_scan": lll_scan}, "lll_already_bad")
        return

    print()
    print(f"LLL state is clean. Running BKZ tour-by-tour, β={BETA}...")
    print(f"Will stop at the first tour with a non-positive r_val.")
    print(f"Per-tour cost: ~5-15 minutes wall (single-threaded MPFR).")
    print()

    flags = BKZ.MAX_LOOPS | BKZ.AUTO_ABORT
    history = []
    first_bad_tour = None

    for t in range(1, MAX_TOURS_TO_TRY + 1):
        t0 = time.time()
        param = BKZ.Param(BETA, max_loops=1, flags=flags)
        BKZ.reduction(B, param, float_type="mpfr", precision=PRECISION)
        elapsed = time.time() - t0

        M = GSO.Mat(B)
        M.update_gso()
        scan = scan_get_r(M, dim, m, label=f"tour {t}")
        scan["tour"] = t
        scan["wall_seconds"] = round(elapsed, 2)
        history.append(scan)

        msg = (f"  tour {t:>2}: {elapsed:>6.1f}s, "
               f"n_bad={scan['n_bad']}, "
               f"min_positive_r={scan['min_positive_r']:.4e}")
        print(msg, flush=True)

        if scan["found"]:
            first_bad_tour = t
            print()
            print("=" * 72)
            print(f"FIRST NON-POSITIVE r_val DETECTED AT TOUR {t}")
            print("=" * 72)
            for bp in scan["bad_positions"]:
                print(f"  position {bp['position']} "
                      f"(active block index {bp['active_block_index']}):")
                print(f"    raw repr:   {bp['raw_repr']}")
                print(f"    raw str:    {bp['raw_str']}")
                print(f"    as float:   {bp['as_float']}")
                print(f"    negative?   {bp['is_negative']}")
                print(f"    zero?       {bp['is_zero']}")
                print(f"    nan?        {bp['is_nan']}")
            print()

            # Save and stop
            save({
                "lll_scan": lll_scan,
                "first_bad_tour": first_bad_tour,
                "history": history,
            }, "found_bad_value")
            return

    # Ran all tours without finding a bad value
    print()
    print(f"Ran {MAX_TOURS_TO_TRY} tours without triggering the clamp.")
    print(f"This is unexpected — seed 1 is known to be degenerate at "
          f"the final state.")
    save({
        "lll_scan": lll_scan,
        "first_bad_tour": None,
        "history": history,
    }, "no_bad_found")


if __name__ == "__main__":
    main()
