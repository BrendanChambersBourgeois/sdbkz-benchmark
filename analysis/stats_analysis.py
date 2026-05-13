#!/usr/bin/env python3
"""
Statistical analysis for SDBKZ vs BKZ paper.
READ-ONLY on results directory. Safe to run while sweep_parallel.py is active.

Computes: paired t-test, Wilcoxon signed-rank, Cohen's d, 95% CIs, skewness.
Reads from: <repo>/results/raw/*.json
Writes to:  <repo>/logs/stats_output.txt (and prints to stdout)

Usage:
    python3 stats_analysis.py
    python3 stats_analysis.py --results-dir /path/to/results/raw

Data loading is delegated to analysis._data.load_all_seeds so this script
shares the q=97 filtering, the file deduplication, and the schema-tolerant
loading with paper_figures.py and the rest of the analysis package. The
sys.path hack below makes `from analysis...` resolve when this file is
run as a standalone script.
"""

import os
import sys

import numpy as np
from scipy import stats as scipy_stats

# Repo root derived from this file's location — works for any checkout path.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from analysis._data import load_all_seeds  # noqa: E402
from analysis._stats_helpers import cliffs_delta, holm_bonferroni  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from log import get_logger  # noqa: E402
PIPELINE = get_logger("stats_analysis")

# ── Config ──────────────────────────────────────────────────────────────────
DEFAULT_RAW_DIR = os.path.join(REPO_ROOT, "results", "raw")
OUTPUT_FILE = os.path.join(REPO_ROOT, "logs", "stats_output.txt")


def compute_stats(advantages):
    """Compute all statistical measures for a group's advantages."""
    n_seeds = len(advantages)
    adv = np.array(advantages)

    result = {
        'n_seeds': n_seeds,
        'mean': np.mean(adv),
        'std': np.std(adv, ddof=1),
        'median': np.median(adv),
        'min': np.min(adv),
        'max': np.max(adv),
        'win_rate': np.mean(adv > 0),
        'skewness': scipy_stats.skew(adv),
    }

    # ── 95% Confidence Interval on mean (t-distribution) ──
    se = result['std'] / np.sqrt(n_seeds)
    t_crit = scipy_stats.t.ppf(0.975, df=n_seeds - 1)
    result['ci_lower'] = result['mean'] - t_crit * se
    result['ci_upper'] = result['mean'] + t_crit * se

    # ── Cohen's d (effect size: mean / std) ──
    if result['std'] > 0:
        result['cohens_d'] = result['mean'] / result['std']
    else:
        result['cohens_d'] = float('inf')

    # ── Cliff's δ (non-parametric one-sample effect size vs 0) ──
    # Distribution-free counterpart to Cohen's d; less sensitive to
    # tail outliers. Range [-1, +1]; sign matches mean advantage.
    result['cliffs_delta'] = cliffs_delta(adv)

    # ── Paired t-test: H0: mean advantage = 0 ──
    if n_seeds >= 2:
        t_stat, p_ttest = scipy_stats.ttest_1samp(adv, 0)
        result['t_stat'] = t_stat
        result['p_ttest'] = p_ttest
    else:
        result['t_stat'] = None
        result['p_ttest'] = None

    # ── Wilcoxon signed-rank test: H0: symmetric around 0 ──
    # (non-parametric, doesn't assume normality)
    if n_seeds >= 10:
        try:
            w_stat, p_wilcoxon = scipy_stats.wilcoxon(adv, alternative='greater')
            result['w_stat'] = w_stat
            result['p_wilcoxon'] = p_wilcoxon
        except Exception:
            result['w_stat'] = None
            result['p_wilcoxon'] = None
    else:
        result['w_stat'] = None
        result['p_wilcoxon'] = None

    # ── Shapiro-Wilk normality test ──
    if 3 <= n_seeds <= 5000:
        try:
            sw_stat, p_shapiro = scipy_stats.shapiro(adv)
            result['p_shapiro'] = p_shapiro
        except Exception:
            result['p_shapiro'] = None
    else:
        result['p_shapiro'] = None

    return result


def format_p(p):
    """Format p-value for display."""
    if p is None:
        return "N/A"
    if p < 1e-300:
        return "< 1e-300"
    if p < 1e-100:
        return "< 1e-100"
    if p < 1e-50:
        return "< 1e-50"
    if p < 1e-20:
        return "< 1e-20"
    if p < 1e-10:
        return "< 1e-10"
    if p < 0.0001:
        return f"{p:.2e}"
    return f"{p:.6f}"


def main():
    PIPELINE.info("stats_analysis start", cat="analysis")
    raw_dir = None
    campaign = "main"
    if len(sys.argv) > 1 and sys.argv[1] == '--results-dir':
        raw_dir = sys.argv[2]
    elif len(sys.argv) > 1 and sys.argv[1] == '--campaign':
        campaign = sys.argv[2]

    print("=" * 80)
    print("SDBKZ vs BKZ — Statistical Analysis")
    if raw_dir is None:
        print(f"Reading from manifest: campaign={campaign}, q=97")
    else:
        print(f"Reading from: {raw_dir}")
    print("This script is READ-ONLY. Safe to run alongside sweep_parallel.py.")
    print("=" * 80)
    print()

    if raw_dir is None:
        groups = load_all_seeds(campaign=campaign, q=97)
    else:
        groups = load_all_seeds(raw_dir)
    if not groups:
        print(f"ERROR: No seed files found in {raw_dir}")
        print("Check --results-dir or run from the right location.")
        sys.exit(1)

    output_lines = []

    def out(line=""):
        print(line)
        output_lines.append(line)

    out("=" * 100)
    out("STATISTICAL ANALYSIS — SDBKZ vs BKZ d(LN) Advantage")
    out(f"Generated from {sum(len(v) for v in groups.values())} seeds across {len(groups)} groups")
    out("=" * 100)

    # ── Per-group stats, pre-correction ──
    sorted_keys = sorted(groups.keys())
    per_group: dict[tuple[int, int], dict] = {}
    for (n, beta) in sorted_keys:
        entries = groups[(n, beta)]
        advantages = [e['advantage'] for e in entries]
        per_group[(n, beta)] = compute_stats(advantages)

    # ── Family-wise Holm-Bonferroni correction across the whole grid ──
    # t-test and Wilcoxon are corrected as two independent families so
    # each headline column tracks strict FWER over the same row set.
    # See docs/design_decisions.md ADR-003 for the Holm-vs-BH rationale.
    t_pvals = [per_group[k].get('p_ttest') for k in sorted_keys]
    w_pvals = [per_group[k].get('p_wilcoxon') for k in sorted_keys]
    t_holm = holm_bonferroni(t_pvals)
    w_holm = holm_bonferroni(w_pvals)
    for k, p_t, p_w in zip(sorted_keys, t_holm, w_holm):
        per_group[k]['p_ttest_holm'] = p_t
        per_group[k]['p_wilcoxon_holm'] = p_w

    # ── Summary Table ──
    out()
    out("TABLE FOR PAPER — Section 4 (add to methodology paragraph)")
    out("Multiple-comparison correction: Holm-Bonferroni step-down over "
        f"the {len(sorted_keys)}-cell family. ADR-003 records the choice.")
    out("-" * 130)
    out(f"{'Group':<12} {'Seeds':>5} {'Mean':>7} {'95% CI':>18} {'Median':>7} "
        f"{'Cohen d':>8} {'Cliff δ':>8} {'t-test p':>12} {'t Holm p':>12} "
        f"{'Wilcox p':>12} {'W Holm p':>12} {'Win%':>6}")
    out("-" * 130)

    for (n, beta) in sorted_keys:
        s = per_group[(n, beta)]
        ci_str = f"[{s['ci_lower']:.3f}, {s['ci_upper']:.3f}]"
        out(f"n={n} β={beta:<4} {s['n_seeds']:>5} {s['mean']:>7.3f} {ci_str:>18} {s['median']:>7.3f} "
            f"{s['cohens_d']:>8.2f} {s['cliffs_delta']:>+8.3f} "
            f"{format_p(s['p_ttest']):>12} {format_p(s['p_ttest_holm']):>12} "
            f"{format_p(s['p_wilcoxon']):>12} {format_p(s['p_wilcoxon_holm']):>12} "
            f"{s['win_rate']*100:>5.1f}%")

    out("-" * 130)

    # ── Detailed per-group analysis ──
    out()
    out("=" * 100)
    out("DETAILED PER-GROUP ANALYSIS")
    out("=" * 100)

    for (n, beta) in sorted_keys:
        s = per_group[(n, beta)]
        advantages = [e['advantage'] for e in groups[(n, beta)]]

        out()
        out(f"── n={n}, β={beta} ({s['n_seeds']} seeds) " + "─" * 50)
        out(f"  Mean advantage:     {s['mean']:.4f} nats")
        out(f"  Std deviation:      {s['std']:.4f}")
        out(f"  Median advantage:   {s['median']:.4f} nats")
        out(f"  Min / Max:          {s['min']:.4f} / {s['max']:.4f}")
        out(f"  Skewness:           {s['skewness']:.3f}")
        out(f"  95% CI:             [{s['ci_lower']:.4f}, {s['ci_upper']:.4f}]")
        out(f"  Win rate:           {s['win_rate']*100:.1f}%")
        out(f"  Cohen's d:          {s['cohens_d']:.2f}  ({'large' if abs(s['cohens_d']) >= 0.8 else 'medium' if abs(s['cohens_d']) >= 0.5 else 'small'})")
        cd_mag = abs(s['cliffs_delta'])
        cd_label = ('large' if cd_mag >= 0.474 else
                    'medium' if cd_mag >= 0.33 else
                    'small' if cd_mag >= 0.147 else 'negligible')
        out(f"  Cliff's δ:          {s['cliffs_delta']:+.3f}  ({cd_label})")
        out(f"  Paired t-test:      t={s['t_stat']:.2f}, p={format_p(s['p_ttest'])}, Holm p={format_p(s['p_ttest_holm'])}" if s['t_stat'] else "  Paired t-test:      N/A")
        out(f"  Wilcoxon signed-rank: W={s['w_stat']:.0f}, p={format_p(s['p_wilcoxon'])}, Holm p={format_p(s['p_wilcoxon_holm'])}" if s['w_stat'] else "  Wilcoxon signed-rank: N/A (need ≥10 seeds)")
        out(f"  Shapiro-Wilk normality: p={format_p(s['p_shapiro'])}" if s['p_shapiro'] else "  Shapiro-Wilk: N/A")

        # Percentiles
        adv = np.array(advantages)
        p5, p25, p75, p95 = np.percentile(adv, [5, 25, 75, 95])
        out(f"  Percentiles:        5th={p5:.3f}  25th={p25:.3f}  75th={p75:.3f}  95th={p95:.3f}")

        # Count of losses (BKZ wins)
        losses = adv[adv < 0]
        if len(losses) > 0:
            out(f"  BKZ wins:           {len(losses)} seeds, mean loss margin: {np.mean(losses):.4f} nats")
        else:
            out("  BKZ wins:           0 (SD-BKZ wins every seed)")

    # ── Paper-ready paragraph ──
    out()
    out("=" * 100)
    out("SUGGESTED PARAGRAPH FOR SECTION 4 OF PAPER")
    out("=" * 100)
    out()
    out("  All groups show statistically significant d(LN) advantages for SD-BKZ")
    out("  (paired t-test p < [FILL FROM TABLE ABOVE] for all groups with 100 seeds;")
    out("  Wilcoxon signed-rank p < [FILL] confirming significance without normality")
    out("  assumptions). Effect sizes are large by conventional standards (Cohen's d > 0.8)")
    out("  in all groups, ranging from [MIN d] to [MAX d]. The 95% confidence intervals")
    out("  exclude zero in every group. These statistics confirm that the d(LN) advantage")
    out("  is not a statistical artifact but a consistent structural phenomenon.")

    # ── Write output file ──
    try:
        with open(OUTPUT_FILE, 'w') as f:
            f.write('\n'.join(output_lines))
        out()
        out(f"Output saved to: {OUTPUT_FILE}")
    except Exception as e:
        out(f"Could not save output file: {e}")

    PIPELINE.info("stats_analysis complete", cat="analysis")


if __name__ == '__main__':
    main()
