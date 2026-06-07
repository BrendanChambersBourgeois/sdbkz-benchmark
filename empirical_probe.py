#!/usr/bin/env python3
"""Tiny empirical probe: does real BKZ d(LN) deviate from the estimator's BEST
model (CN11 simulator), and how does the deviation scale with beta?

Decisive feasibility test. For small (dim, beta) we CAN run real BKZ; deployed
beta~400 we cannot, so the question is whether the deviation TREND extrapolates.
- d(real, GSA)  : deviation from naive GSA (known to be nonzero; estimator
                  already corrects this via the simulator).
- d(real, CN11) : deviation from the estimator's accurate BKZ simulator. THIS
                  is the novel quantity. If ~0, the estimator already captures
                  reality -> NO-GO. If nonzero AND not shrinking with beta -> GO.

d(.,.) = mean abs difference of slope-removed log GS profiles (paper-1 style,
reference-free between the two profiles -- no fixed point needed).
Runs in sdbkz-benchmark:ci (fpylll). Tiny: dim 70, few seeds, threads=1.
"""
import math
import statistics as st

from fpylll import FPLLL, GSO, IntegerMatrix, LLL, BKZ
from fpylll.tools.bkz_simulator import simulate


def real_profile(dim, beta, seed):
    FPLLL.set_random_seed(seed)
    A = IntegerMatrix.random(dim, "qary", k=dim // 2, bits=30)
    LLL.reduction(A)
    BKZ.reduction(A, BKZ.Param(block_size=beta, max_loops=20,
                               flags=BKZ.MAX_LOOPS))
    M = GSO.Mat(A, float_type="double")
    M.update_gso()
    return [0.5 * math.log(M.get_r(i, i)) for i in range(dim)]


def gsa_line(profile):
    """slope-removed: subtract the best-fit straight line -> shape only."""
    n = len(profile)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(profile) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((xs[i] - mx) * (profile[i] - my) for i in range(n))
    slope = sxy / sxx
    inter = my - slope * mx
    return [profile[i] - (slope * xs[i] + inter) for i in range(n)]


def cn11_profile(dim, beta, seed):
    FPLLL.set_random_seed(seed)
    A = IntegerMatrix.random(dim, "qary", k=dim // 2, bits=30)
    LLL.reduction(A)
    M = GSO.Mat(A, float_type="double")
    M.update_gso()
    r, _ = simulate(M, BKZ.Param(block_size=beta, max_loops=20))
    return [0.5 * math.log(x) for x in r]


def dln(p, q):
    a, b = gsa_line(p), gsa_line(q)
    return sum(abs(a[i] - b[i]) for i in range(len(a))) / len(a)


def main():
    dim, seeds = 50, 3
    print(f"dim={dim}, {seeds} seeds. d(.,.) = mean|slope-removed profile diff|",
          flush=True)
    print(f"{'beta':>5} {'d(real,GSA)':>12} {'d(real,CN11)':>13} {'ratio CN11/GSA':>15}",
          flush=True)
    for beta in (10, 20, 30, 40):
        dg, dc = [], []
        for s in range(1, seeds + 1):
            rp = real_profile(dim, beta, s)
            cp = cn11_profile(dim, beta, s)
            # naive GSA = the best-fit line itself -> d(real,GSA)=mean|shape|
            shape = gsa_line(rp)
            dg.append(sum(abs(v) for v in shape) / len(shape))
            dc.append(dln(rp, cp))
        mg, mc = st.mean(dg), st.mean(dc)
        print(f"{beta:>5} {mg:>12.4f} {mc:>13.4f} {mc/mg if mg else 0:>15.2f}",
              flush=True)


if __name__ == "__main__":
    main()
