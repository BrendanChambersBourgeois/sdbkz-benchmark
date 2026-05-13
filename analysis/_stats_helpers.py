"""Statistical helpers for SD-BKZ vs BKZ paper tables.

Two additions on top of the v1.5.0 stats pipeline:

- `cliffs_delta(advantages)` — non-parametric one-sample effect size,
  computed against the constant zero. Distribution-free counterpart to
  Cohen's d. Asymmetry between the two flags groups where Cohen's d is
  inflated by tail outliers; the paper now reports both side-by-side.

- `holm_bonferroni(pvalues)` — Holm step-down family-wise error rate
  correction. Strict FWER control across the 33-cell (n, β) grid. ADR-003
  in `docs/design_decisions.md` records the choice of Holm vs Benjamini–
  Hochberg (FDR): the family is small (33), the cost of a false claim
  in a paper headline table is asymmetric to the cost of an over-correction,
  and Holm dominates Bonferroni at no additional assumption.

Both functions are pure-input, pure-output. Raw uncorrected p-values
flowing into `holm_bonferroni` must remain bit-identical to the v1.5.0
output of `analysis/stats_analysis.py`; this is enforced by the bit-
identity gate in CHANGELOG Unreleased.
"""
from __future__ import annotations

from typing import Iterable, Optional

import numpy as np


def cliffs_delta(advantages: Iterable[float]) -> float:
    """One-sample Cliff's δ against the constant zero.

    Cliff's δ between two samples is (#(x>y) - #(y>x)) / (n*m). For the
    one-sample comparison against the constant 0 this collapses to
    (#(a>0) - #(a<0)) / n, which is the canonical distribution-free
    effect-size analogue of Cohen's d when the reference is a fixed point.

    Range: [-1, 1]. δ = +1 means SD-BKZ wins every seed; δ = -1 means BKZ
    wins every seed; δ = 0 means equal counts. Magnitude interpretation
    (Romano et al.): negligible <0.147, small <0.33, medium <0.474, large
    otherwise.

    No SHA-256 schema mutation: this function reads `advantage` values
    that are already present in every per-seed JSON since v1.0.
    """
    adv = np.asarray(list(advantages), dtype=float)
    n = adv.size
    if n == 0:
        return 0.0
    wins = int(np.sum(adv > 0))
    losses = int(np.sum(adv < 0))
    return (wins - losses) / n


def holm_bonferroni(
    pvalues: Iterable[Optional[float]],
) -> list[Optional[float]]:
    """Holm step-down adjusted p-values, preserving input order.

    Implementation: sort the non-null p-values ascending; multiply the
    i-th smallest by (m − i + 1) where m is the count of non-null
    p-values; cumulative-max for monotonicity; cap each adjusted value at
    1.0. `None` entries pass through unchanged so callers can mark
    under-powered groups (n_seeds < 10 for Wilcoxon) without spuriously
    inflating the correction family size.

    The correction family is the entire grid passed in a single call —
    so the 33-cell t-test family is corrected as a unit and the Wilcoxon
    family is corrected as a separate unit, exactly as a paper-grade
    headline table should report.
    """
    pvals = list(pvalues)
    indexed: list[tuple[int, float]] = [
        (i, float(p)) for i, p in enumerate(pvals) if p is not None
    ]
    if not indexed:
        return [None] * len(pvals)

    indexed.sort(key=lambda t: t[1])
    m = len(indexed)
    running = 0.0
    adjusted: list[Optional[float]] = [None] * len(pvals)
    for rank, (orig_idx, p) in enumerate(indexed):
        scaled = p * (m - rank)
        running = max(running, scaled)
        adjusted[orig_idx] = min(1.0, running)
    return adjusted
