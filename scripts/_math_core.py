"""Canonical numerical helpers for the SD-BKZ benchmark.

v1.2 consolidation target (Phase 1). Currently holds only the pure-math
helpers that are duplicated across sweep_parallel.py, sweep_cloud.py,
and q3329_verify.py. Phase 2 will add `build_lwe_kannan`, `_log_clamp`,
`_safe_log_r`; Phase 3 will add `_metrics_from_gso` — each gated on
verify.sh SHA-256 bit-identity proof.

For now: new scripts import `ln_fixed_point` from this module. The
three legacy scripts keep their character-identical local copies until
Phase 2 replaces them with an import from here.

CLAUDE.md §3 (q=3329 lessons): "check raw values, not derived metrics"
— if this module's output ever disagrees with a legacy copy, trust the
legacy copy and flag the bug, because the legacy copies are what
produced the paper's SHA-256-stable seed JSONs.
"""
import math


def ln_fixed_point(size, beta):
    """Closed-form Li-Nguyen fixed-point GS-log-norm profile.

    Pure function of (size, beta). Returns a list of length ``size``
    giving the predicted log-norms of Gram-Schmidt vectors at the
    BKZ fixed point, per Li-Nguyen (2020).

    Character-identical to the copies in:
      scripts/sweep_parallel.py:115
      scripts/sweep_cloud.py (corresponding line)
      scripts/q3329_verify.py (corresponding line)

    Any edit to the math here MUST preserve equality with the three
    legacy copies until Phase 2 of the v1.2 consolidation removes them.
    """
    exp = (size - 1) / (2 * (beta - 1)) + (beta * (beta - 2)) / (
        2 * size * (beta - 1)
    )
    log_v_beta = math.log(beta / (2 * math.pi * math.e)) * exp
    log_delta = math.log(beta / (2 * math.pi * math.e)) / (2 * beta - 2)
    total_vol = sum((size + 1 - 2 * i) * log_delta for i in range(1, size + 1))
    profile, cum = [], 0.0
    for i in range(1, size + 1):
        cum += (size + 1 - 2 * i) * log_delta
        profile.append(cum - (i / size) * total_vol)
    return [p + log_v_beta for p in profile]
