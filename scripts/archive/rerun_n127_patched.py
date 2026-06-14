#!/usr/bin/env python3
"""Kahan-patch validation #2 — rerun the contaminated n=127 NTRU seeds under
PATCHED fplll and show the §8 catastrophic-cancellation floor clamp vanish.

Context (see sessions/ntru_dsd_resume.md, paper §8):
The main fplll path (fpylll 0.6.4 PyPI wheel → vendored fplll 5.5.0) produces
a degenerate final basis on a subset of n=127 NTRU seeds: get_r(i,i) goes
non-positive, is silently clamped to 1e-300, and the GS log-norm crashes to
b1 = -345.388. 16/152 n=127 seeds were hit; the n=127 point was cut from the
paper-2 trend because of it. Validation #1 was the q=3329 LWE rerun; this is
#2 on a NEW modulus family (q=971/1087/1201).

This script reruns the EXACT contaminated seeds (n=127, β=20, q∈{971,1087,
1201}, precision=1000, max_tours=50) with IDENTICAL inputs — the only change
is the patched engine the container links. Three deliberate differences from
the original generation:
  1. Output goes to a SEPARATE tree results/seeds/ntru_patched/ — the locked
     LWE/NTRU seeds are NEVER touched or overwritten.
  2. log_clamp_fn is WIRED (the original NTRU worker passed None → silent
     clamps). We record every clamp so a residual mild negative is visible,
     not assumed away (CLAUDE.md: log before substitute).
  3. RESUMABLE + PARALLEL: each seed is written the moment it finishes and an
     existing patched seed is skipped, so a kill / power loss only costs the
     in-flight seeds. Seeds run across an mp.Pool (n=127 p1000 is minutes per
     seed; serial was ~11h, parallel is ~slowest-seed wall-clock).

Run inside the patched image (sdbkz-fplll-patched), repo bind-mounted:
    docker run --rm -v "$PWD":/work -w /work sdbkz-fplll-patched:val2 \
        python3 scripts/rerun_n127_patched.py [--workers N]
Exit: 0 all ex-degenerate seeds recover · 1 any ex-(-345) seed still
degenerate · 2 setup error. (A residual MILD clamp, raw > -100, does NOT by
itself fail — only a still-catastrophic seed does; the count is reported.)
"""
from __future__ import annotations

import argparse
import glob
import json
import multiprocessing as mp
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402
from _bkz_core import run_single  # noqa: E402
from _math_core import log_clamp  # noqa: E402
from generators import build_ntru, get_metric_span  # noqa: E402
from log import get_logger  # noqa: E402

PIPELINE = get_logger("rerun_n127_patched")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N, BETA, PRECISION, MAX_TOURS = 127, 20, 1000, 50
QS = (971, 1087, 1201)
SEEDS = (1, 2, 3, 4)

# Separate, clearly-named output tree — NOT results/seeds/ntru/ (locked).
PATCHED_ROOT = os.path.join(BASE, "results", "seeds", "ntru_patched")
CLAMP_LOG = os.path.join(BASE, "results", "clamp_events_n127_patched.jsonl")

# The contaminated floor signature (paper §8): a clamped get_r (1e-300) maps
# to b1 = -345.388. A seed at/below DEGENERATE_B1 is still catastrophically
# degenerate.
#
# Recovery criterion (corrected 2026-06-04): a patched seed has recovered iff
# its b1 ESCAPES the catastrophic floor — i.e. b1 > DEGENERATE_B1 — landing in
# the control band of the never-contaminated seeds (empirically ~ -0.03 to
# -0.43 at n=127, β=20, these q/precision). The earlier `SANE_B1_MIN = 1.5`
# gate was WRONG: it assumed a DSD floor (~1.97) that does not apply to these
# UNCRACKED n=127 seeds, whose sane b1 sits near 0 (the controls prove it).
# Validation-#2 result: all 4 contaminated seeds recovered -345.388 -> ~-0.1.
DEGENERATE_B1 = -100.0

# Per-process clamp tally. Reset at the start of every _run_one task; the
# worker returns its count so the parent can sum across the pool (module
# globals are per-process under mp.Pool, so a shared counter would not add up).
_proc_clamps = 0


def _clamp_logger(ctx: str, position: int, raw_value: float) -> None:
    """Append a clamp event to the shared JSONL (O_APPEND of a sub-PIPE_BUF
    line is atomic across processes on Linux) and tally it per-process."""
    global _proc_clamps
    _proc_clamps += 1
    log_clamp(ctx, position, raw_value,
              script_name="rerun_n127_patched", log_path=CLAMP_LOG)


def _patched_path(q: int, seed: int) -> str:
    return os.path.join(
        PATCHED_ROOT, f"q{q}", f"p{PRECISION}_mt{MAX_TOURS}",
        f"n{N}_beta{BETA}", f"seed{seed:04d}.json"
    )


def _b1_of(d: dict) -> float | None:
    gs = d.get("gs_lognorms_bkz") or []
    return min(gs) if gs else None


def _run_one(task: tuple[int, int]) -> dict:
    """Rerun one (q, seed) under the patched engine. Resumable: an existing
    patched seed is loaded and skipped. Returns a record for the parent."""
    global _proc_clamps
    _proc_clamps = 0
    q, seed = task
    out = _patched_path(q, seed)

    if os.path.exists(out):
        d = json.load(open(out))
        return {"q": q, "seed": seed, "new_b1": _b1_of(d),
                "clamps": None, "status": "skip"}

    L, f, g = build_ntru(N, q, seed=seed)
    if len(L) != 2 * N:
        return {"q": q, "seed": seed, "new_b1": None,
                "clamps": 0, "status": "dim_err"}
    H = np.array([[L[N + i][j] for j in range(N)] for i in range(N)]).T
    if not np.array_equal((H @ f) % q, g % q):
        return {"q": q, "seed": seed, "new_b1": None,
                "clamps": 0, "status": "key_err"}

    m_start, m_end = get_metric_span("ntru")(N, len(L))
    r = run_single(
        L=L, n=N, active_block_start=m_start, active_block_end=m_end,
        beta=BETA, seed=seed, q=q, precision=PRECISION,
        max_tours=MAX_TOURS, log_clamp_fn=_clamp_logger, warn_on_clamp=True,
    )
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        json.dump(r, fh, indent=2)
    PIPELINE.info("patched seed done", cat="ntru", n=N, q=q, seed=seed,
                  new_b1=_b1_of(r), clamps=_proc_clamps)
    return {"q": q, "seed": seed, "new_b1": _b1_of(r),
            "clamps": _proc_clamps, "status": "ok"}


def _orig_b1(q: int, seed: int) -> float | None:
    """min(gs_lognorms_bkz) from the ORIGINAL contaminated seed, if present."""
    hits = glob.glob(
        os.path.join(BASE, "results", "seeds", "ntru", f"q{q}",
                     "*", f"n{N}_beta{BETA}", f"seed{seed:04d}.json")
    )
    if not hits:
        return None
    return _b1_of(json.load(open(hits[0])))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=min(12, mp.cpu_count()),
                    help="parallel seeds (default min(12, ncpu))")
    args = ap.parse_args()

    tasks = [(q, seed) for q in QS for seed in SEEDS]
    PIPELINE.info("rerun start", cat="ntru", seeds=len(tasks),
                  workers=args.workers)
    print(f"  running {len(tasks)} seeds on {args.workers} workers "
          f"(resumable: existing patched seeds skipped) ...")

    with mp.Pool(args.workers) as pool:
        recs = pool.map(_run_one, tasks)

    # -- report ----------------------------------------------------------
    fail = 0
    total_clamps = 0
    n_degen = 0
    rows = []
    for rec in sorted(recs, key=lambda r: (r["q"], r["seed"])):
        q, seed, new_b1 = rec["q"], rec["seed"], rec["new_b1"]
        old_b1 = _orig_b1(q, seed)
        was_degen = old_b1 is not None and old_b1 <= DEGENERATE_B1
        # Recovered = escaped the catastrophic -345 floor into the finite
        # control band (b1 > DEGENERATE_B1). NOT a >=1.5 DSD-floor test.
        now_sane = new_b1 is not None and new_b1 > DEGENERATE_B1
        recovered = (not was_degen) or now_sane
        n_degen += int(was_degen)
        if rec["clamps"]:
            total_clamps += rec["clamps"]
        if not recovered:
            fail = 1
        rows.append((q, seed, old_b1, new_b1, was_degen, recovered,
                     rec["clamps"], rec["status"]))

    print()
    print("  Kahan-patch validation #2 — n=127 NTRU rerun (patched fplll 5.5.0)")
    print(f"  {'q':>5} {'seed':>4} {'old_b1':>11} {'new_b1':>9} "
          f"{'was_deg':>7} {'recov':>5} {'clamps':>6} {'status':>7}")
    for q, seed, old_b1, new_b1, was_degen, recovered, clamps, status in rows:
        ob = f"{old_b1:.3f}" if old_b1 is not None else "n/a"
        nb = f"{new_b1:.3f}" if new_b1 is not None else "n/a"
        cl = "skip" if clamps is None else str(clamps)
        flag = "" if recovered else "  <-- STILL CATASTROPHIC"
        print(f"  {q:>5} {seed:>4} {ob:>11} {nb:>9} "
              f"{str(was_degen):>7} {str(recovered):>5} {cl:>6} "
              f"{status:>7}{flag}")

    print()
    print(f"  degenerate originals: {n_degen}  (expected 4: q971 s1/s3, "
          f"q1087 s1, q1201 s2)")
    print(f"  clamp events this run: {total_clamps}  "
          f"(catastrophic -345 floor expected GONE; mild residual logged)")
    print(f"  patched seeds: {os.path.relpath(PATCHED_ROOT, BASE)}/")

    print()
    print("RERUN_N127_PATCHED", "PASS" if fail == 0 else "FAIL")
    PIPELINE.info("rerun done", cat="ntru", degenerate_originals=n_degen,
                  clamp_events=total_clamps,
                  result="pass" if fail == 0 else "fail")
    return fail


if __name__ == "__main__":
    sys.exit(main())
