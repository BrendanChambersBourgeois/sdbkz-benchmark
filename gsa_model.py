#!/usr/bin/env python3
"""Feasibility probe (#1 estimator d(LN)) -- the estimator's GSA side, no Sage.

The lattice-estimator (malb) models a BKZ-beta-reduced basis by the Geometric
Series Assumption (GSA): the Gram-Schmidt log-norms fall on a STRAIGHT LINE
with slope set by the root-Hermite factor delta_beta. This file reimplements
just that model (closed form, no Sage) so we can ask the probe's question:
does real BKZ d(LN) deviate from this assumed line enough to move bit-security?

We do NOT run the estimator; we reproduce its GSA assumption analytically and
print the assumed profile + the primal-uSVP success beta at deployed params.
"""
import math


def delta_beta(beta: int) -> float:
    """Root-Hermite factor delta for BKZ-beta (the estimator's GSA00 model).
    delta = ( (beta/(2*pi*e)) * (pi*beta)**(1/beta) )**(1/(2*(beta-1)))."""
    if beta <= 1:
        return 1.0219  # LLL-ish floor
    b = beta
    return ((b / (2 * math.pi * math.e)) * (math.pi * b) ** (1.0 / b)) ** (
        1.0 / (2.0 * (b - 1))
    )


def gsa_slope(beta: int) -> float:
    """Per-index slope of the GSA log-profile: log b*_i = log b*_0 - i*(2 ln delta).
    (natural log). Real BKZ profiles are compared against this straight line."""
    return -2.0 * math.log(delta_beta(beta))


def gsa_profile(dim: int, log_vol: float, beta: int):
    """Assumed GS log-norm profile (natural log) under GSA for a lattice of the
    given dimension and log-volume. Straight line, pinned so sum == log_vol."""
    s = gsa_slope(beta)
    # log b*_i = c + s*i ; sum_i (c + s*i) = log_vol  -> solve c.
    c = (log_vol - s * dim * (dim - 1) / 2.0) / dim
    return [c + s * i for i in range(dim)]


# ---- deployed NIST params (published estimator-class optimal primal attacks) ----
# (name, n_lwe, q, ~optimal beta, ~embedding dim d, classical core-SVP bits).
# Values are the well-known estimator outputs (Kyber/Dilithium NIST round-3
# era), used here only to fix the regime we'd need to reach.
DEPLOYED = [
    ("Kyber512   (NIST-1)", 512, 3329, 406, 1025, 118),
    ("Kyber768   (NIST-3)", 768, 3329, 623, 1473, 182),
    ("Dilithium2 (NIST-2)", 1024, 8380417, 423, 2049, 123),
]


def core_svp_bits(beta: int) -> float:
    """Classical core-SVP cost exponent (estimator's conservative model):
    0.292*beta. The number the estimator REPORTS as bit-security."""
    return 0.292 * beta


def main():
    print("=== estimator GSA assumption: delta_beta + slope across beta ===")
    print(f"{'beta':>5} {'delta':>9} {'slope(nat/idx)':>15} {'core-SVP bits':>13}")
    for beta in (20, 30, 40, 60, 100, 200, 300, 406, 500):
        print(f"{beta:>5} {delta_beta(beta):>9.5f} {gsa_slope(beta):>15.6f}"
              f" {core_svp_bits(beta):>13.1f}")
    print()
    print("=== deployed params: regime we'd need d(LN) to bite at ===")
    print(f"{'param':>22} {'beta':>5} {'dim':>5} {'bits':>5} {'GSA slope':>10}")
    for name, n, q, beta, d, bits in DEPLOYED:
        print(f"{name:>22} {beta:>5} {d:>5} {bits:>5} {gsa_slope(beta):>10.6f}")
    print()
    print("=== the lever: d bits per +/-1 in effective beta (0.292) ===")
    print("  A d(LN)-driven correction moves bit-security only if it changes the")
    print("  EFFECTIVE beta at the uSVP crossing. 1 beta ~ 0.292 classical bits.")
    print("  So a profile deviation worth a paper must shift effective beta by")
    print("  >~3-5 (>~1-1.5 bits) at deployed beta~400, robustly.")


if __name__ == "__main__":
    main()
