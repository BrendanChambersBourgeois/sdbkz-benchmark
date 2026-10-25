"""Canonical numerical helpers for the SD-BKZ benchmark.

Single source for `ln_fixed_point`, `build_lwe_kannan`, `metrics_from_gso` and
the defensive-clamp logger `log_clamp`. Every runner imports these; the
published seed JSONs were produced by byte-identical copies, so any change
here must be proven against them (verify.sh, parity tests).
"""
from __future__ import annotations

import datetime
import json
import math
import os
from collections.abc import Callable
from typing import Any, Optional

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
    `sweep_parallel.py`, `q3329_verify.py`, `run_3x_extended.py` and
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
                "ts": datetime.datetime.now(datetime.UTC).isoformat(),
                "script": script_name,
                "ctx": ctx,
                "position": int(position),
                "raw_value": float(raw_value),
            }) + "\n")
    except OSError:
        pass


# build_lwe_kannan moved to generators/lwe_kannan.py (generators refactor,
# 2026-06-03). Re-exported here so the seven existing importers keep working
# unchanged mid-refactor; later steps repoint them at `generators` directly.
# The move is verbatim — bases stay byte-identical (SHA-256 manifest gate).
from generators.lwe_kannan import build_lwe_kannan  # noqa: E402,F401


def metrics_from_gso(
    M: Any,
    dim: int,
    m: int,
    ln_profile: list[float],
    full: bool = False,
    clamp_ctx: str = "",
    log_clamp_fn: Optional[Callable[[str, int, float], None]] = None,
    warn_on_clamp: bool = False,
    active_end: Optional[int] = None,
) -> dict[str, Any]:
    """Extract metrics from an already-updated fpylll GSO object.

    Always returns ``{"rankin": [...], "dln": float}`` computed over
    the active block ``[m, active_end)`` (``active_end`` defaults to
    ``dim`` — the historical full-tail behaviour). The generator owns the
    span; the engine is metric-blind. With ``full=True`` also includes
    the full-basis (``[0, dim)``) Gram-Schmidt log-norms and the Root
    Hermite Factor — that range is always the whole basis, independent of
    the active block.

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
    end = active_end if active_end is not None else dim
    start, size = m, end - m
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

    gs_log_active = [_safe_log_r(i, "active") for i in range(start, end)]
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

    Character-identical to the copy in scripts/sweep_parallel.py.

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
