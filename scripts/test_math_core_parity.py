#!/usr/bin/env python3
"""Bit-identity parity check: _math_core vs legacy copies.

Verifies `_math_core.ln_fixed_point` and `_math_core.build_lwe_kannan`
return element-wise equal results to the copies in each legacy sweep
script, across a grid of (n, β, seed) values covering the full paper
sweep plus small-parameter edge cases.

Exit code 0 = every legacy copy agrees with _math_core bit-for-bit.
Exit code 1 = any disagreement; prints first few differing entries.

Post-Phase 2/3 the "legacy" references are re-exports from _math_core,
so this test is load-bearing only as a regression guard: if someone
adds a bespoke local def back to a sweep script, the check will catch
the drift immediately.

Usage: python3 scripts/test_math_core_parity.py
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

from log import get_logger  # noqa: E402

PIPELINE = get_logger("test_math_core_parity")

# Mock argv so the target modules' import-time argparse doesn't choke
_saved = sys.argv
sys.argv = ["dummy.py"]
import overnight_experiments  # noqa: E402
import run_3x_extended  # noqa: E402
import run_convergence_test  # noqa: E402
import sweep_cloud  # noqa: E402
import sweep_parallel  # noqa: E402
from _math_core import (
    build_lwe_kannan as canonical_blwe,
)
from _math_core import (  # noqa: E402
    ln_fixed_point as canonical_ln,
)

sys.argv = ["q3329_verify.py", "--n", "100", "--beta", "30",
            "--seeds", "1", "--precision", "250"]
import q3329_verify  # noqa: E402

sys.argv = _saved

LN_LEGACY = {
    "sweep_parallel": sweep_parallel.ln_fixed_point,
    "sweep_cloud": sweep_cloud.ln_fixed_point,
    "q3329_verify": q3329_verify.ln_fixed_point,
    "overnight_experiments": overnight_experiments.ln_fixed_point,
    "run_3x_extended": run_3x_extended.ln_fixed_point,
    "run_convergence_test": run_convergence_test.ln_fixed_point,
}

BLWE_LEGACY = {
    "sweep_parallel": sweep_parallel.build_lwe_kannan,
    "sweep_cloud": sweep_cloud.build_lwe_kannan,
    "q3329_verify": q3329_verify.build_lwe_kannan,
    "overnight_experiments": overnight_experiments.build_lwe_kannan,
    "run_3x_extended": run_3x_extended.build_lwe_kannan,
    "run_convergence_test": run_convergence_test.build_lwe_kannan,
}

LN_GRID = [
    (n, beta)
    for n in [20, 50, 70, 80, 90, 100, 110, 120, 130, 140, 150, 200]
    for beta in [3, 10, 20, 30, 40]
]

BLWE_GRID = [
    (n, m, q, seed)
    for n in [20, 50, 100]
    for m in [20, 50]
    for q in [97, 3329]
    for seed in [1, 42, 123]
]


def _compare_blwe(ref, other):
    """Compare two (L, s, e) tuples from build_lwe_kannan."""
    L_ref, s_ref, e_ref = ref
    L_oth, s_oth, e_oth = other
    if L_ref != L_oth:
        return False
    if not (s_ref == s_oth).all():
        return False
    if not (e_ref == e_oth).all():
        return False
    return True


def _ln_check():
    failures = []
    for n, beta in LN_GRID:
        ref = canonical_ln(n, beta)
        for name, fn in LN_LEGACY.items():
            if ref != fn(n, beta):
                failures.append(("ln_fixed_point", name, n, beta))
    return failures, len(LN_GRID) * len(LN_LEGACY)


def _blwe_check():
    failures = []
    for n, m, q, seed in BLWE_GRID:
        ref = canonical_blwe(n, m, q, seed=seed)
        for name, fn in BLWE_LEGACY.items():
            if not _compare_blwe(ref, fn(n, m, q, seed=seed)):
                failures.append(("build_lwe_kannan", name, f"n={n} m={m} q={q} seed={seed}"))
    return failures, len(BLWE_GRID) * len(BLWE_LEGACY)


def main():
    PIPELINE.info(
        "math_core parity check start",
        cat="validation",
        ln_pairs=len(LN_GRID), ln_legacy=list(LN_LEGACY.keys()),
        blwe_pairs=len(BLWE_GRID), blwe_legacy=list(BLWE_LEGACY.keys()),
    )

    ln_fails, ln_total = _ln_check()
    blwe_fails, blwe_total = _blwe_check()
    failures = ln_fails + blwe_fails
    total = ln_total + blwe_total

    print(f"ln_fixed_point:   {len(LN_GRID)} pairs × "
          f"{len(LN_LEGACY)} copies = {ln_total} comparisons")
    print(f"build_lwe_kannan: {len(BLWE_GRID)} pairs × "
          f"{len(BLWE_LEGACY)} copies = {blwe_total} comparisons")
    print(f"Total: {total} comparisons, {len(failures)} failure(s)")

    if not failures:
        print("PASS — every legacy copy bit-identical to _math_core.")
        PIPELINE.info(
            "math_core parity check pass",
            cat="validation", comparisons=total, failures=0,
        )
        return 0

    print("FAIL — first 5 disagreement(s):")
    for entry in failures[:5]:
        print(f"  {entry}")
    if len(failures) > 5:
        print(f"  ... {len(failures) - 5} more")
    PIPELINE.error(
        "math_core parity check fail",
        cat="validation", comparisons=total, failures=len(failures),
        first_disagreement=str(failures[0]),
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
