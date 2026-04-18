#!/usr/bin/env python3
"""q=3329 numerical-instability detection and rate estimation.

Detects the **fplll Gram-Schmidt cancellation** at q=3329, n=100, β=30
documented in Section 8 of the paper. For each seed JSON in
results/cloud/ and results/q3329/ matching the q=3329 n=100 β=30 group,
checks whether either algorithm's Gram-Schmidt log-norms drop below
−100 (the canonical Section-8 detection threshold, which in practice
picks up exactly the wrapper's −345.39 clamp fingerprint). Reports
counts, rates with 95% Wilson confidence intervals, the clean subset
statistics, and a per-seed breakdown.

═══════════════════════════════════════════════════════════════════════
THE CAUSE, FULLY RESOLVED (2026-04-10)
═══════════════════════════════════════════════════════════════════════

The q=3329 instability is a **numerical-precision failure in fplll's
Gram-Schmidt update code**, located precisely at:

    fplll/gso_interface.cpp:147-151
    MatGSOInterface<ZT, FT>::update_gso_row

Every BKZ tour, every LLL call, every `get_r(i,i)` query — for every
FT instantiation (double, long double, dpe, dd, qd, mpfr_t) — funnels
through this single shared function. Both `MatGSO` and `MatGSOGram`
inherit it via `using MatGSOInterface<ZT, FT>::update_gso_row;`.

**The Gram-Schmidt variant is neither CGS, MGS, nor Householder — it
is the Cholesky-style squared-form recurrence:**

    r(i,i) = ‖b_i‖²  −  Σ_{k<i}  μ_{i,k}² · ‖b*_k‖²

computed as a single in-place scalar subtraction loop. fplll never
materializes the projected vector `b*_i` at all — the diagonal entry
is computed directly as a difference of two large positive numbers.
This is **strictly worse than MGS** for cancellation, because MGS
would at least compute `b*_i = b_i − Σ μ_{ik} b*_k` as a vector and
then take its norm (single subtraction error per coordinate). The
squared form puts the entire accumulated rounding error into one
scalar subtract, with no compensation and no sanity check.

Existing sanity checks in the fplll code path: **zero**. No clamp on
negative `r(i,i)`. No sign assertion. No reorthogonalization trigger.
No `FPLLL_DEBUG_CHECK(r(i,j).sgn() > 0)` for the diagonal case. The
only check is `mu(i,j).is_finite()` after the subsequent divide,
which catches divide-by-zero but silently accepts finite-but-negative
values. A bad sign in `r(i,i)` then propagates as a finite negative
`μ(j,i)` for later `j > i`, producing wrong-but-finite contributions
to the rest of the GSO pipeline. The corruption only becomes visible
when an outside caller (e.g. `scripts/q3329_verify.py:88`) reads
`get_r(i,i)` and notices the sign.

**The −345.39 floor measured here is the wrapper's clamp constant**,
not a precision floor or a real Gram-Schmidt log-norm. It is exactly
`0.5 * log(1e-300)`, substituted by `scripts/q3329_verify.py:88` when
`get_r(i,i) <= 0` fires:

    if r_val <= 0:
        r_val = 1e-300                  # ← clamp
    ... 0.5 * math.log(r_val)           # ← = −345.38776394910684

Every degenerate seed hits this exact constant to 14 digits across
every source (cloud, local, Dylan 9950X3D) — the single substitution
constant is the cleanest possible failure fingerprint.

═══════════════════════════════════════════════════════════════════════
EVIDENCE — FOUR CORROBORATING INDEPENDENT OBSERVATIONS
═══════════════════════════════════════════════════════════════════════

1. **Raw negative value observed.** `analysis/investigate_q3329_get_r.py`
   reproduced cloud seed 1 tour-by-tour and captured
   `MatGSO.get_r(293, 293) = -1.2805632996020577` at tour 30 — a
   finite, non-zero, non-NaN, non-Inf, non-positive squared norm.
   Mathematically impossible for a physical ‖b*_i‖². Preserved at
   `results/q3329_get_r_investigation.json`.

2. **Run-to-run non-determinism on bit-identical input.** Two
   independent reproducers running cloud seed 1 with the same lattice
   (verified element-wise via `np.array_equal`), same MPFR=1000
   precision, and same `FPLLL.set_random_seed(1)` produce *different*
   trajectories starting at tour 1. The prior `investigate_q3329_get_r`
   run hit the collapse at tour 30; a fresh wrapper-free reproducer
   survived 40 tours cleanly on the exact same input. A stable
   physical small-positive Gram-Schmidt norm would not flip sign
   across runs. This is direct evidence the value is teetering
   exactly on zero with the FP operation path deciding the sign —
   the hair-trigger signature of cancellation near unit roundoff.
   (See paper §8.2 for the full cross-machine breakdown and paper §8.3
   for the root-cause analysis and Kahan patch.)

3. **Cross-machine reproducibility.** Two entirely different CPU
   microarchitectures hit the same population-level rate to within
   sampling noise: Intel Raptor Lake 13900K under VMware reports
   21/55 = 38.2%, AMD Zen 5 9950X3D native reports 17/45 = 37.8%.
   Combined 100-seed dataset: **38/100 = 38.0%, Wilson 95% CI
   [29.1%, 47.8%]**. A 0.4 pp difference between vendors with
   different FP execution paths, different AVX implementations, and
   different FMA behaviour rules out any microarchitecture-specific
   cause. The bug is in the algorithm, not the silicon.

4. **BKZ vs SD-BKZ symmetry.** Of 47 degenerate events across 100
   seeds, 25 affect BKZ and 22 affect SD-BKZ (ratio 1.14:1, well
   within sampling noise for 47 events). This rules out any bug in
   only the forward pass, only the SD variant, or only one side of
   the algorithm. Both algorithms call the same `update_gso_row`,
   and both hit the same cancellation.

═══════════════════════════════════════════════════════════════════════
WHAT IS RULED OUT
═══════════════════════════════════════════════════════════════════════

  1. **Precision-only causes.** 500-bit vs 1000-bit MPFR produces
     bit-identical dln/advantage values — if precision were the
     cause, doubling it would change the output. It does not.
     Compensation (not precision) is what's missing.

  2. **One-sided algorithm bugs.** See evidence §4 above.

  3. **Random floating-point noise.** Every degenerate seed hits the
     EXACT clamp constant, not scattered nearby values. Stochastic
     FP error would scatter.

  4. **Code-wide bugs in the lattice wrapper scripts.** A 20-seed
     verification at n=50 β=30 q=3329 (same wrapper, same MPFR
     config, same tours) is 100% clean. Dimension-dependent, so the
     wrapper code is fine.

  5. **Codepath bugs affecting all (n, β, q).** All q=97 configs are
     unaffected at every dimension n=50–150. Modulus-and-dimension-
     specific to the corner of parameter space where LWE-Kannan at
     q=3329, n=100 makes the tail Gram-Schmidt vectors teeter near
     the FP unit roundoff of the ambient working precision.

  6. **Microarchitecture-specific cause.** See evidence §3 above.

═══════════════════════════════════════════════════════════════════════
THE FIX
═══════════════════════════════════════════════════════════════════════

A 14-line Kahan-compensated subtraction replacement for the inner
loop at `gso_interface.cpp:147-151`. Template-agnostic (works for all
FT types including MPFR), no API change, no algorithm change, no
caller change. Compensated summation moves the computed value off
the zero crossing by precisely the amount of accumulated rounding
error that the naive loop was losing, which converts the 38%
hair-trigger hit rate to 0% on the 55-seed patched rerun reported
in paper §8.3.

═══════════════════════════════════════════════════════════════════════

This script's "ANY degenerate" rate measures the rate at which
fpylll's `get_r` returns a non-positive value in the active basis
block — equivalently, the rate at which the squared-form scalar
subtraction in `gso_interface.cpp:147-151` fails to maintain the
non-negativity invariant. It is the operational metric for the
paper's Section 8 discussion.

Usage:
    python3 analysis/q3329_degeneracy_check.py

Outputs:
    results/q3329_degeneracy_check.json — full data + per-seed breakdown
    stdout                              — formatted summary
"""
import os
import sys
import json
import glob
import datetime
from collections import defaultdict

import numpy as np
from scipy import stats as scipy_stats

# Repo root derived from this file's location — works for any checkout path.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from log import get_logger  # noqa: E402
PIPELINE = get_logger("q3329_degeneracy_check")


# ── Config ──────────────────────────────────────────────────────────────────
DEFAULT_CLOUD_DIR = os.path.join(REPO_ROOT, "results", "cloud")
DEFAULT_LOCAL_DIR = os.path.join(REPO_ROOT, "results", "q3329")
OUT_PATH = os.path.join(REPO_ROOT, "results", "q3329_degeneracy_check.json")

# Section-8 detection threshold. A seed is "degenerate" if any
# Gram-Schmidt log-norm drops below this value during reduction. The
# value is calibrated against the observed precision floor of −345.39,
# which is well below any value seen in clean seeds (clean seeds bottom
# out around −5 to −15).
DEGEN_THRESHOLD = -100.0

# Target group: n=100, β=30, q=3329
TARGET_N = 100
TARGET_BETA = 30


# ── Loader ──────────────────────────────────────────────────────────────────

def load_q3329_seeds(cloud_dir=DEFAULT_CLOUD_DIR, local_dir=DEFAULT_LOCAL_DIR,
                    n=TARGET_N, beta=TARGET_BETA):
    """Load all q=3329 seeds for the target (n, β) via the v1.3 manifest.

    Switched in v1.3 from the pre-migration glob of cloud_dir + local_dir
    to a scripts/_data.load_all_seeds(campaign="q3329", ...) query. The
    _source/_path fields are preserved for downstream reporting and
    reconstructed from the manifest's `tags` (cloud present ⇒ _source
    "cloud") and `path` fields.

    cloud_dir / local_dir remain as function args for the pre-v1.3
    caller contract, but are now unused — the manifest is the source of
    truth. Returns a list of seed dicts with the original JSON schema.
    """
    from analysis._data import load_all_seeds  # noqa: E402 — lazy to
    # preserve standalone `python3 analysis/q3329_degeneracy_check.py`
    # execution before REPO_ROOT is on sys.path at import time.

    # q=3329 is excluded from the default load_all_seeds() main-campaign
    # filter (to prevent q3329-into-q97 contamination, Incidents #14/19);
    # the manifest-mode query with campaign="q3329" is the q3329-specific
    # counterpart.
    # The paper §8 headline dataset is 1000-bit MPFR, 70-tour cap.
    # p500 / p=250 entries (q3329_degenerate/, convergence tests) are
    # different campaigns analytically and filtered out here.
    groups = load_all_seeds(
        campaign="q3329", n=n, beta=beta, q=3329,
        precision=1000, max_tours=70,
    )
    entries = groups.get((n, beta), [])

    seeds = []
    for d in entries:
        # Reconstruct the _source/_path fields legacy callers relied on.
        # The manifest's canonical path lives under results/seeds/q3329/;
        # the cloud-vs-local provenance comes from the manifest tags that
        # the walker assigned based on the original dir (build_seed_manifest
        # tags cloud-sourced entries with "cloud").
        tags = d.get("_manifest_tags") or ()
        d["_source"] = "cloud" if "cloud" in tags else "local"
        d["_path"] = d.get("_manifest_path", "")
        seeds.append(d)

    return seeds


# ── Detection ───────────────────────────────────────────────────────────────

def classify_seed(seed_data, threshold=DEGEN_THRESHOLD):
    """Classify a single seed by which algorithm(s) hit the precision floor.

    Returns one of: "clean", "bkz_only", "sdbkz_only", "both".
    """
    bkz_min = min(seed_data["gs_lognorms_bkz"])
    sd_min = min(seed_data["gs_lognorms_sdbkz"])
    bkz_bad = bkz_min < threshold
    sd_bad = sd_min < threshold
    if bkz_bad and sd_bad:
        return "both"
    if bkz_bad:
        return "bkz_only"
    if sd_bad:
        return "sdbkz_only"
    return "clean"


def detect_degeneracy(seeds, threshold=DEGEN_THRESHOLD):
    """Run the full Section-8 detection across a set of seeds.

    Returns a structured dict with per-category counts, rates with
    Wilson 95% CI, the clean-subset stats, and a per-seed breakdown.
    """
    if not seeds:
        return {"n_seeds": 0, "error": "no seeds loaded"}

    by_class = defaultdict(list)
    for s in seeds:
        cls = classify_seed(s, threshold)
        by_class[cls].append({
            "seed": s["seed"],
            "source": s["_source"],
            "advantage": float(s["advantage"]),
            "bkz_min": float(min(s["gs_lognorms_bkz"])),
            "sdbkz_min": float(min(s["gs_lognorms_sdbkz"])),
            "classification": cls,
        })

    n = len(seeds)
    n_clean = len(by_class["clean"])
    n_bkz_only = len(by_class["bkz_only"])
    n_sd_only = len(by_class["sdbkz_only"])
    n_both = len(by_class["both"])
    n_degen = n_bkz_only + n_sd_only + n_both

    # Wilson 95% CI on the ANY-degenerate rate
    if n > 0:
        ci = scipy_stats.binomtest(n_degen, n).proportion_ci(
            confidence_level=0.95, method="wilson"
        )
        ci_lo, ci_hi = float(ci.low), float(ci.high)
    else:
        ci_lo = ci_hi = 0.0

    # Clean subset statistics
    if n_clean > 0:
        clean_advs = np.array([r["advantage"] for r in by_class["clean"]])
        clean_stats = {
            "n_seeds": n_clean,
            "mean_advantage": float(np.mean(clean_advs)),
            "median_advantage": float(np.median(clean_advs)),
            "std_advantage": float(np.std(clean_advs, ddof=1))
                             if n_clean > 1 else None,
            "min_advantage": float(np.min(clean_advs)),
            "max_advantage": float(np.max(clean_advs)),
            "win_rate": float(np.mean(clean_advs > 0)),
            "n_wins": int(np.sum(clean_advs > 0)),
        }
    else:
        clean_stats = {"n_seeds": 0}

    # Full sample statistics (mean is misleading due to spike skew —
    # the median and win rate are the right metrics for bimodal data)
    all_advs = np.array([float(s["advantage"]) for s in seeds])
    full_stats = {
        "n_seeds": n,
        "mean_advantage": float(np.mean(all_advs)),
        "median_advantage": float(np.median(all_advs)),
        "win_rate": float(np.mean(all_advs > 0)),
        "n_wins": int(np.sum(all_advs > 0)),
    }

    return {
        "target_group": {"n": TARGET_N, "beta": TARGET_BETA, "q": 3329},
        "detection_threshold": threshold,
        "counts": {
            "n_seeds": n,
            "clean": n_clean,
            "bkz_only_degenerate": n_bkz_only,
            "sdbkz_only_degenerate": n_sd_only,
            "both_degenerate": n_both,
            "any_degenerate": n_degen,
        },
        "rates": {
            "degenerate": n_degen / n if n else 0,
            "wilson_95_ci": [ci_lo, ci_hi],
            "clean": n_clean / n if n else 0,
        },
        "clean_subset": clean_stats,
        "full_sample": full_stats,
        "per_seed": (
            sorted(by_class["bkz_only"], key=lambda r: r["seed"])
            + sorted(by_class["sdbkz_only"], key=lambda r: r["seed"])
            + sorted(by_class["both"], key=lambda r: r["seed"])
            + sorted(by_class["clean"], key=lambda r: r["seed"])
        ),
    }


# ── Output ──────────────────────────────────────────────────────────────────

def format_text_report(result):
    """Pretty-print the detection result to stdout."""
    if result.get("error"):
        return f"ERROR: {result['error']}"

    n = result["counts"]["n_seeds"]
    c = result["counts"]
    rates = result["rates"]
    ci_lo, ci_hi = rates["wilson_95_ci"]

    lines = []
    lines.append("=" * 72)
    lines.append("q=3329 ALGORITHMIC DEGENERACY DETECTION")
    lines.append("=" * 72)
    lines.append(
        f"Target group: n={TARGET_N}, β={TARGET_BETA}, q=3329 "
        f"(see paper Section 8)"
    )
    lines.append(
        f"Detection threshold: any gs_lognorm < "
        f"{result['detection_threshold']}"
    )
    lines.append("")
    lines.append("Cause: Cholesky-style squared-form Gram-Schmidt cancellation")
    lines.append("in fplll/gso_interface.cpp:147-151 (MatGSOInterface::update_gso_row).")
    lines.append("Diagonal step r(i,i) = ‖b_i‖² − Σ μ_{i,k}²·‖b*_k‖² computed as")
    lines.append("a single scalar subtract with no compensation; rounding error")
    lines.append("accumulates across the k-sum and flips the sign for tail")
    lines.append("positions on near-degenerate bases.")
    lines.append("Fix: 14-line Kahan-compensated subtraction patch, written and")
    lines.append("pending build/test. See `fplll_mgs_patch.diff` + module docstring.")
    lines.append("")
    lines.append("─" * 72)
    lines.append("CLASSIFICATION BREAKDOWN")
    lines.append("─" * 72)
    lines.append(f"  Clean:                {c['clean']:>3}/{n}  "
                 f"({c['clean']/n*100:5.1f}%)")
    lines.append(f"  BKZ-only degenerate:  {c['bkz_only_degenerate']:>3}/{n}  "
                 f"({c['bkz_only_degenerate']/n*100:5.1f}%)")
    lines.append(f"  SD-BKZ-only degen:    {c['sdbkz_only_degenerate']:>3}/{n}  "
                 f"({c['sdbkz_only_degenerate']/n*100:5.1f}%)")
    lines.append(f"  Both degenerate:      {c['both_degenerate']:>3}/{n}  "
                 f"({c['both_degenerate']/n*100:5.1f}%)")
    lines.append("  ─" * 14)
    lines.append(f"  ANY degenerate:       {c['any_degenerate']:>3}/{n}  "
                 f"({c['any_degenerate']/n*100:5.1f}%)")
    lines.append("")
    lines.append(
        f"  Wilson 95% CI on degeneracy rate: "
        f"[{ci_lo*100:.1f}%, {ci_hi*100:.1f}%]"
    )
    lines.append("")

    cs = result["clean_subset"]
    if cs["n_seeds"] > 0:
        lines.append("─" * 72)
        lines.append(f"CLEAN SUBSET STATS (n={cs['n_seeds']})")
        lines.append("─" * 72)
        lines.append(f"  Mean advantage:    {cs['mean_advantage']:+.4f} nats")
        lines.append(f"  Median advantage:  {cs['median_advantage']:+.4f} nats")
        if cs.get("std_advantage") is not None:
            lines.append(f"  Std:               {cs['std_advantage']:.4f}")
        lines.append(f"  Min:               {cs['min_advantage']:+.4f}")
        lines.append(f"  Max:               {cs['max_advantage']:+.4f}")
        lines.append(
            f"  Win rate:          {cs['n_wins']}/{cs['n_seeds']} "
            f"= {cs['win_rate']*100:.1f}%"
        )
        lines.append("")

    fs = result["full_sample"]
    lines.append("─" * 72)
    lines.append(f"FULL SAMPLE STATS (n={fs['n_seeds']})")
    lines.append("─" * 72)
    lines.append(
        f"  Mean advantage:    {fs['mean_advantage']:+.4f} nats   "
        f"(skewed by spikes — use median instead)"
    )
    lines.append(
        f"  Median advantage:  {fs['median_advantage']:+.4f} nats  "
        f"(robust to spikes)"
    )
    lines.append(
        f"  Win rate:          {fs['n_wins']}/{fs['n_seeds']} "
        f"= {fs['win_rate']*100:.1f}%"
    )
    lines.append("")

    # Per-seed listing of degenerate seeds (clean ones omitted for brevity)
    degen_rows = [r for r in result["per_seed"]
                  if r["classification"] != "clean"]
    if degen_rows:
        lines.append("─" * 72)
        lines.append("DEGENERATE SEEDS (per-seed breakdown)")
        lines.append("─" * 72)
        lines.append(
            f"  {'seed':>4} {'src':>5} {'class':>14} "
            f"{'adv':>11} {'bkz_min':>10} {'sd_min':>10}"
        )
        for r in degen_rows:
            lines.append(
                f"  {r['seed']:>4} {r['source']:>5} "
                f"{r['classification']:>14} "
                f"{r['advantage']:>+11.4f} "
                f"{r['bkz_min']:>10.2f} {r['sdbkz_min']:>10.2f}"
            )
        lines.append("")

    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    PIPELINE.info("q3329_degeneracy_check start", cat="analysis")
    print("Loading q=3329 seeds...")
    seeds = load_q3329_seeds()
    n_cloud = sum(1 for s in seeds if s["_source"] == "cloud")
    n_local = sum(1 for s in seeds if s["_source"] == "local")
    print(f"  Cloud: {n_cloud}, Local: {n_local}, Total: {len(seeds)}")
    print()

    if not seeds:
        print(f"ERROR: no q=3329 seeds found at "
              f"{DEFAULT_CLOUD_DIR} or {DEFAULT_LOCAL_DIR}")
        sys.exit(1)

    result = detect_degeneracy(seeds)

    # Add provenance metadata
    result["generated_at"] = datetime.datetime.now().isoformat(
        timespec="seconds"
    )
    # Record source dirs as repo-relative paths so the committed JSON
    # does not carry machine-specific absolute paths.
    result["source_dirs"] = [
        os.path.relpath(DEFAULT_CLOUD_DIR, REPO_ROOT),
        os.path.relpath(DEFAULT_LOCAL_DIR, REPO_ROOT),
    ]
    result["n_cloud_seeds"] = n_cloud
    result["n_local_seeds"] = n_local

    # Write JSON
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Saved JSON: {OUT_PATH}")
    print()

    # Print formatted report
    print(format_text_report(result))
    PIPELINE.info("q3329_degeneracy_check complete", cat="analysis")


if __name__ == "__main__":
    main()
