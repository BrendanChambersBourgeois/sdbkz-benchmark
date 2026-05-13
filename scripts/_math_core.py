"""Canonical numerical helpers for the SD-BKZ benchmark.

v1.2 consolidation target. Holds the pure-math helpers that are
duplicated across `sweep_parallel.py`, `sweep_cloud.py`, and
`q3329_verify.py` (per the 2026-04-17 code_complexity audit).

Roadmap (each phase is its own commit on `v1.2-consolidation`):

  Phase 1 (DONE)  — Add canonical `ln_fixed_point` here. Legacy copies
                    untouched. Parity test in
                    `scripts/test_math_core_parity.py` proves
                    bit-identity across a 60-pair (n, β) grid.
  Phase 2 (DONE)  — Swap three legacy `ln_fixed_point` defs out for
                    `from _math_core import ln_fixed_point`. Verified
                    bit-identical n=50 β=20 seed 1 via `verify.sh`.
  Phase 3 (DONE)  — Add `build_lwe_kannan` here. Swap six legacy
                    copies (all six were already byte-identical per
                    SHA-256 check) out for `from _math_core import
                    build_lwe_kannan`. Same verify.sh gate.
  Phase 4 (DONE)  — `metrics_from_gso` lives below; the interface
                    accepts a `log_clamp_fn` callback (binds each
                    caller's log sink), a `clamp_ctx` tag, a
                    `warn_on_clamp` opt-in (q=3329 verification path),
                    and the `n_clamped` counter is folded into the
                    callback rather than returned. Four legacy callers
                    now hold 3–7 line wrappers that delegate here:
                      sweep_parallel.py        → _log_clamp
                      sweep_cloud.py           → _log_clamp_cloud
                      q3329_verify.py          → _log_clamp + warn_on_clamp
                      overnight_experiments.py → _log_clamp
                    `_bkz_core.py` uses the canonical form directly.
                    `run_3x_extended.py` and `run_convergence_test.py`
                    retain inline `_safe_log_r` closures (active-block
                    rankin only, no full-dict return) for SHA-256
                    stability of their paper-cited seed JSONs; migrate
                    opportunistically only if those scripts ever need
                    a behaviour change.

CLAUDE.md §3 (q=3329 lessons): "check raw values, not derived metrics"
— if this module's output ever disagrees with a legacy copy, trust the
legacy copy and flag the bug, because the legacy copies are what
produced the paper's SHA-256-stable seed JSONs.
"""
from __future__ import annotations

import datetime
import json
import math
import os
from typing import Any, Callable, Optional

import numpy as np

# -- Tunable constants -------------------------------------------------------
# Sentinel value substituted for fpylll's ``M.get_r(i, i)`` when it
# returns a non-positive number. Logged via ``log_clamp_fn`` before
# the substitution fires so the raw value stays auditable. Mirrored
# in scripts/_bkz_core.py as CLAMP_FLOOR_R for the BKZ driver.
CLAMP_FLOOR_R: float = 1e-300


def log_clamp(
    ctx: str,
    position: int,
    raw_value: float,
    *,
    script_name: str,
    log_path: str,
) -> None:
    """Append one defensive-clamp event to a JSONL side log. Never raises.

    Canonical implementation of the defensive-clamp logger used by
    `sweep_parallel.py`, `sweep_cloud.py`, `q3329_verify.py`,
    `overnight_experiments.py`, `run_3x_extended.py`, and
    `run_convergence_test.py`. Each caller keeps a thin wrapper
    `_log_clamp(ctx, position, raw_value)` that supplies its own
    `script_name` + `log_path` (the cloud variant points at a
    container-local path that gets uploaded to S3 alongside each
    per-seed result).

    Writes an append-only JSONL record:

        {"ts": "...", "script": "<name>", "ctx": "...", "position": int,
         "raw_value": float}

    POSIX atomic-append semantics (writes < PIPE_BUF = 4096 B) make
    this safe under multiprocessing workers. Never raises on OSError
    so a log write failure cannot block compute.
    """
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "script": script_name,
                "ctx": ctx,
                "position": int(position),
                "raw_value": float(raw_value),
            }) + "\n")
    except OSError:
        pass


def build_lwe_kannan(
    n: int, m: int, q: int, seed: int = 123
) -> tuple[list[list[int]], np.ndarray, np.ndarray]:
    """Construct an LWE-Kannan embedding lattice of dimension n+m+1.

    Pure function of (n, m, q, seed) — seeded numpy RandomState makes
    lattice generation deterministic. Returns ``(L, s, e)`` where
    ``L`` is a nested-list ``(n+m+1) x (n+m+1)`` integer matrix,
    ``s`` the secret, and ``e`` the error vector.

    Character-identical to the legacy copies in (Phase 3 swap):
      scripts/sweep_parallel.py, scripts/sweep_cloud.py,
      scripts/q3329_verify.py, scripts/overnight_experiments.py,
      scripts/run_3x_extended.py, scripts/run_convergence_test.py
    """
    rng = np.random.RandomState(seed)
    s = rng.randint(0, 2, n).astype(int)
    e = rng.choice([-1, 0, 1], m).astype(int)
    A = rng.randint(0, q, (m, n)).astype(int)
    b = (A @ s + e) % q
    dim = m + n + 1
    L = [[0] * dim for _ in range(dim)]
    for i in range(m):
        L[i][i] = q
    for j in range(n):
        for i in range(m):
            L[m + j][i] = int(A[i][j])
    for j in range(n):
        L[m + j][m + j] = 1
    for i in range(m):
        L[m + n][i] = int(b[i])
    L[m + n][m + n] = 1
    return L, s, e


def metrics_from_gso(
    M: Any,
    dim: int,
    m: int,
    ln_profile: list[float],
    full: bool = False,
    clamp_ctx: str = "",
    log_clamp_fn: Optional[Callable[[str, int, float], None]] = None,
    warn_on_clamp: bool = False,
) -> dict[str, Any]:
    """Extract metrics from an already-updated fpylll GSO object.

    Always returns ``{"rankin": [...], "dln": float}`` computed over
    the active block ``[m, dim)``. With ``full=True`` also includes
    the full-basis Gram-Schmidt log-norms and the Root Hermite Factor.

    Defensive clamps: when ``M.get_r(i, i)`` returns a non-positive
    value (the Cholesky-style cancellation described in paper §8,
    surfaced at q=3329 n>=100), the raw value is routed to
    ``log_clamp_fn`` (typically each caller's thin wrapper around
    ``log_clamp`` — so the event lands in `results/clamp_events.jsonl`
    or the cloud container's ``/tmp/clamp_events.jsonl``) before the
    ``1e-300`` substitution fires. The per-seed JSON schema is NOT
    mutated on clamp; SHA-256 reproducibility is preserved.

    ``warn_on_clamp=True`` emits one stdout line per call summarising
    the active-block clamp count. Opt-in so the quiet q=97 main sweep
    stays quiet; the q=3329 verification wrapper enables it for a
    fast-signal during the long runs at the ML-KEM modulus.

    ``log_clamp_fn`` may be ``None`` for tests or code paths that
    deliberately want the silent 1e-300 substitute without side
    effects. All existing callers pass a real logger.
    """
    start, size = m, dim - m
    n_clamped = 0

    def _safe_log_r(i: int, ctx_tag: str) -> float:
        nonlocal n_clamped
        r = M.get_r(i, i)
        if r > 0:
            return 0.5 * math.log(r)
        n_clamped += 1
        if log_clamp_fn is not None:
            log_clamp_fn(f"{clamp_ctx} {ctx_tag}".strip(), i, r)
        return 0.5 * math.log(CLAMP_FLOOR_R)

    gs_log_active = [_safe_log_r(i, "active") for i in range(start, dim)]
    if warn_on_clamp and n_clamped > 0:
        print(f"  WARNING: {n_clamped} get_r values <= 0 "
              f"(logged to results/clamp_events.jsonl)")
    log_vol = sum(gs_log_active)
    rankin, cum = [], 0.0
    for idx, val in enumerate(gs_log_active):
        cum += val
        rankin.append(cum - ((idx + 1) / size) * log_vol)

    dln = float(np.mean(np.abs(np.array(rankin) - np.array(ln_profile))))
    result = {"rankin": rankin, "dln": dln}

    if full:
        gs_all = [_safe_log_r(i, "full") for i in range(dim)]
        log_b1 = gs_all[0]
        log_det_over_dim = sum(gs_all) / dim
        result["gs_lognorms"] = gs_all
        result["rhf"] = math.exp(log_b1 - log_det_over_dim)

    return result


def ln_fixed_point(size: int, beta: int) -> list[float]:
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
