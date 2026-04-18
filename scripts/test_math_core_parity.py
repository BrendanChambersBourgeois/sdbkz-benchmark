#!/usr/bin/env python3
"""Bit-identity parity check: _math_core vs legacy copies.

Verifies that `_math_core.ln_fixed_point` returns element-wise equal
results to the copies in sweep_parallel.py, sweep_cloud.py, and
q3329_verify.py across a grid of (n, β) values that covers the full
paper sweep + edge cases.

Exit code 0 = all three legacy copies agree with _math_core bit-for-bit.
Exit code 1 = any disagreement; prints diff.

Must pass before Phase 2 of the v1.2 consolidation swaps the legacy
copies out for an import from _math_core (because Phase 2 depends on
the copies being character-identical to avoid seed-JSON drift).

Usage: python3 scripts/test_math_core_parity.py
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

# Mock argv so the target modules' import-time argparse doesn't choke
_saved = sys.argv
sys.argv = ["dummy.py"]
from _math_core import ln_fixed_point as canonical  # noqa: E402
import sweep_parallel  # noqa: E402
import sweep_cloud  # noqa: E402
sys.argv = ["q3329_verify.py", "--n", "100", "--beta", "30",
            "--seeds", "1", "--precision", "250"]
import q3329_verify  # noqa: E402
sys.argv = _saved

LEGACY = {
    "sweep_parallel": sweep_parallel.ln_fixed_point,
    "sweep_cloud": sweep_cloud.ln_fixed_point,
    "q3329_verify": q3329_verify.ln_fixed_point,
}

# Full paper sweep grid plus edge cases (β=2 is the degenerate BKZ,
# covered only as a boundary smoke test — paper uses β >= 20).
GRID = [
    (n, beta)
    for n in [20, 50, 70, 80, 90, 100, 110, 120, 130, 140, 150, 200]
    for beta in [3, 10, 20, 30, 40]
]


def main():
    failures = []
    for n, beta in GRID:
        ref = canonical(n, beta)
        for name, fn in LEGACY.items():
            legacy = fn(n, beta)
            if ref != legacy:
                failures.append((name, n, beta, ref, legacy))

    print(f"Tested {len(GRID)} (n, β) pairs across "
          f"{len(LEGACY)} legacy copies.")
    if not failures:
        print("PASS — _math_core.ln_fixed_point is bit-identical to all "
              "three legacy copies across the full grid.")
        return 0

    print(f"FAIL — {len(failures)} disagreement(s):")
    for name, n, beta, ref, legacy in failures[:5]:
        print(f"  {name}  n={n} β={beta}")
        print(f"    canonical[:3] = {ref[:3]}")
        print(f"    legacy[:3]    = {legacy[:3]}")
    if len(failures) > 5:
        print(f"  ... {len(failures) - 5} more")
    return 1


if __name__ == "__main__":
    sys.exit(main())
