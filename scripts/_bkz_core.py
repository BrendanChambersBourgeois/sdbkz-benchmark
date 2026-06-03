"""Canonical BKZ + SD-BKZ per-seed driver.

v1.2 consolidation Phase 5. Factors out the ~150-line `run_single`
duplicated across `sweep_parallel.py`, `sweep_cloud.py`, and
`q3329_verify.py` (per the 2026-04-17 code_complexity audit, which
flagged this as the highest-stakes consolidation target — the q=3329
silent-clamp incident hid in run_single divergence for 9 days).

The canonical `run_single` here takes every behavioural knob as an
explicit keyword argument; each legacy script keeps a thin wrapper
that supplies its own conventions:

  caller          q          precision  max_tours              floor    schema-quirk
  sweep_parallel  Q (97)     PRECISION  TOURS_BY_BETA[beta]    plain    store_per_tour key only when True
  sweep_cloud     q kwarg    p kwarg    TOURS_BY_BETA[beta]    safe     store_per_tour key only when True
  q3329_verify    Q (3329)   PRECISION  MAX_TOURS (import)     safe     store_per_tour key always present

Quirks:
- "plain" floor:  `mean(deltas[-5:])`. Original sweep_parallel form;
  assumes max_tours ≥ 5 (always true for the paper sweep).
- "safe" floor:   guarded by termination + deltas length, falls back
  to last delta. Identical to plain in normal runs (β=20/30/40 with
  paper tour counts), differs only on early stagnation with < 5 tours.
- store_per_tour key always present: q3329_verify has historically
  always emitted this key, so its existing seed JSONs all carry it.
  Wrapper restores after the canonical call to preserve schema.

All three callers feed the same numerical hot loop:

  - LLL-reduce a fresh basis once
  - Per variant (BKZ then SD-BKZ): copy the LLL'd basis, reduce, walk
    tours collecting Rankin / d(LN) / RHF, capture stagnation
  - Compute advantage = bkz_final_dln - sdbkz_final_dln + crossover

LLL is deterministic, so the "re-LLL each variant" pattern in the
original sweep_parallel and the "LLL once + copy" pattern in the
other two produce bit-identical reductions; the canonical uses the
copy pattern uniformly because it is strictly cheaper.
"""
from __future__ import annotations

import datetime
import math
import os
import sys
import time
from collections.abc import Callable
from typing import Any, Optional

import numpy as np
from _math_core import ln_fixed_point, metrics_from_gso
from fpylll import BKZ, FPLLL, GSO, LLL, IntegerMatrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from log import get_logger  # noqa: E402

PIPELINE = get_logger("_bkz_core")

# -- Tunable constants -------------------------------------------------------
# Per-tour delta below which the basis is considered to have stagnated;
# triggers early termination of the BKZ tour loop and captures the final
# Rankin profile + RHF + GS log-norms at the stagnation tour. Matches
# the value used in every legacy run_single copy (sweep_parallel, cloud,
# q3329_verify) at the time of the v1.2 consolidation; lowering it
# means more tours before stagnation is declared, raising it means
# earlier termination.
STAGNATION_THRESHOLD: float = 1e-6

# Sentinel value substituted for fpylll's ``M.get_r(i, i)`` when it
# returns a non-positive number (the Cholesky-style cancellation at
# q=3329 n>=100, paper §8). Logged via ``log_clamp_fn`` before the
# substitution fires so the raw value stays auditable.
CLAMP_FLOOR_R: float = 1e-300

# Emit a heartbeat pipeline.jsonl event every N tours during the
# BKZ/SD-BKZ inner loop so long-running seeds (n>=130, β>=40) leave
# a breadcrumb trail in the centralised log without per-tour bloat.
# Set to 0 to disable heartbeats. DEBUG level — filtered from console
# but visible in pipeline.jsonl analyses.
HEARTBEAT_EVERY: int = 25


def run_single(
    *,
    L: list[list[int]],
    n: int,
    active_block_start: int,
    active_block_end: int,
    beta: int,
    seed: int,
    q: int,
    precision: int,
    max_tours: int,
    log_clamp_fn: Optional[Callable[[str, int, float], None]],
    warn_on_clamp: bool = False,
    store_per_tour: bool = False,
    floor_mode: str = "safe",
    always_emit_store_per_tour: bool = False,
) -> dict[str, Any]:
    """Run BKZ and SD-BKZ on a single (n, beta, seed) lattice.

    Returns a result dict matching the schema of the legacy run_single
    copies. Callers (sweep_parallel, sweep_cloud, q3329_verify)
    supply their per-script knobs as kwargs.
    """
    FPLLL.set_precision(precision)
    FPLLL.set_random_seed(seed)

    # Engine is construction-blind AND metric-blind: it measures the GSO
    # over the active block [m, end) the GENERATOR specifies via its span
    # (LWE-Kannan: [2n, dim) embedded tail; NTRU: [0, dim) full basis) —
    # NOT an engine assumption. The comparison profile spans the active
    # block, length end-m.
    dim = len(L)
    m = active_block_start
    end = active_block_end
    ln_p = ln_fixed_point(end - m, beta)

    result: dict[str, Any] = {
        "n": n, "beta": beta, "seed": seed, "q": q, "max_tours": max_tours,
        "precision": precision, "dim": dim, "m": m, "status": "completed",
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    # The legacy q3329_verify dict-literal placed `store_per_tour` at
    # position 10 unconditionally (True or False); other callers only
    # emit the key when the flag is True. always_emit_store_per_tour
    # preserves the q3329_verify schema position so future re-runs are
    # SHA-256 reproducible against existing q3329 seeds.
    if store_per_tour or always_emit_store_per_tour:
        result["store_per_tour"] = bool(store_per_tour)

    def _metrics(M: Any, full: bool) -> dict[str, Any]:
        return metrics_from_gso(M, dim, m, ln_p, full=full,
                                log_clamp_fn=log_clamp_fn,
                                warn_on_clamp=warn_on_clamp,
                                active_end=end)

    # Initial quality (LLL-reduced, no BKZ yet)
    B_init = IntegerMatrix.from_matrix(L)
    LLL.reduction(B_init)
    M_init = GSO.Mat(B_init)
    M_init.update_gso()
    init = _metrics(M_init, full=True)
    result["initial_dln"] = init["dln"]
    result["initial_rhf"] = init["rhf"]
    result["initial_rankin_profile"] = [float(x) for x in init["rankin"]]
    result["initial_gs_lognorms"] = [float(x) for x in init["gs_lognorms"]]

    for variant in ("bkz", "sdbkz"):
        # LLL is deterministic, so a copy of the already-reduced basis
        # is byte-equivalent to a fresh from_matrix + LLL — saves one
        # LLL pass per variant.
        B = IntegerMatrix(B_init)

        flags = BKZ.MAX_LOOPS | BKZ.AUTO_ABORT
        if variant == "sdbkz":
            flags |= BKZ.SD_VARIANT

        dln_per_tour = []
        deltas = []
        rankin_per_tour = []
        gs_lognorms_per_tour = []
        rhf_per_tour = []
        stag_tour = None
        stag_rankin = None
        stag_rhf = None
        stag_gs = None
        termination = "max_tours_reached"
        prev_rankin = init["rankin"]
        t0 = time.time()

        for t in range(1, max_tours + 1):
            param = BKZ.Param(beta, max_loops=1, flags=flags)
            BKZ.reduction(B, param, float_type="mpfr", precision=precision)

            M = GSO.Mat(B)
            M.update_gso()
            if store_per_tour:
                metrics = _metrics(M, full=True)
                rankin_per_tour.append([float(x) for x in metrics["rankin"]])
                gs_lognorms_per_tour.append(
                    [float(x) for x in metrics["gs_lognorms"]]
                )
                rhf_per_tour.append(float(metrics["rhf"]))
            else:
                metrics = _metrics(M, full=False)
            dln_per_tour.append(metrics["dln"])

            delta = float(np.mean(np.abs(
                np.array(metrics["rankin"]) - np.array(prev_rankin)
            )))
            deltas.append(delta)

            if HEARTBEAT_EVERY and t % HEARTBEAT_EVERY == 0:
                PIPELINE.debug(
                    "tour heartbeat", cat="sweep",
                    n=n, beta=beta, seed=seed, variant=variant,
                    tour=t, max_tours=max_tours,
                    dln=metrics["dln"], delta=delta,
                )

            if delta < STAGNATION_THRESHOLD:
                stag_tour = t
                full_m = _metrics(M, full=True)
                stag_rankin = [float(x) for x in full_m["rankin"]]
                stag_rhf = full_m["rhf"]
                stag_gs = [float(x) for x in full_m["gs_lognorms"]]
                termination = "stagnated"
                break

            prev_rankin = metrics["rankin"]

        elapsed = time.time() - t0
        tours_run = len(dln_per_tour)

        if stag_tour is None:
            stag_tour = tours_run
            M_final = GSO.Mat(B)
            M_final.update_gso()
            full_m = _metrics(M_final, full=True)
            stag_rankin = [float(x) for x in full_m["rankin"]]
            stag_rhf = full_m["rhf"]
            stag_gs = [float(x) for x in full_m["gs_lognorms"]]

        result[f"{variant}_dln_per_tour"] = dln_per_tour
        result[f"{variant}_final_dln"] = dln_per_tour[-1]
        result[f"{variant}_tours_run"] = tours_run
        result[f"{variant}_termination"] = termination
        result[f"stagnation_tour_{variant}"] = stag_tour
        result[f"rankin_profile_{variant}"] = stag_rankin
        result[f"rhf_{variant}"] = stag_rhf
        result[f"gs_lognorms_{variant}"] = stag_gs
        if store_per_tour:
            result[f"{variant}_rankin_per_tour"] = rankin_per_tour
            result[f"{variant}_gs_lognorms_per_tour"] = gs_lognorms_per_tour
            result[f"{variant}_rhf_per_tour"] = rhf_per_tour
        if floor_mode == "safe":
            if termination == "max_tours_reached" and len(deltas) >= 5:
                result[f"{variant}_floor"] = float(np.mean(deltas[-5:]))
            else:
                result[f"{variant}_floor"] = (
                    float(deltas[-1]) if deltas else None
                )
        else:  # "plain" — sweep_parallel legacy form
            result[f"{variant}_floor"] = float(np.mean(deltas[-5:]))
        result[f"{variant}_time"] = elapsed

    result["advantage"] = result["bkz_final_dln"] - result["sdbkz_final_dln"]
    result["rhf_advantage"] = result["rhf_bkz"] - result["rhf_sdbkz"]

    bkz_final = result["bkz_final_dln"]
    crossover = None
    for t_idx, sd_dln in enumerate(result["sdbkz_dln_per_tour"], 1):
        if sd_dln < bkz_final:
            crossover = t_idx
            break
    result["crossover_tour"] = crossover

    return result
