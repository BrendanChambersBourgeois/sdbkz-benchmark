"""Paper-ready text tables for the SD-BKZ benchmark.

table_main_results — Table 2: per-group means, std, win rate, β/n
table_statistics   — Table 3: 95% CIs, Cohen's d, Cliff's δ, t-test /
                     Wilcoxon p-values + Holm-Bonferroni adjusted p-values
table_spatial      — Table 4: head/mid/tail Rankin profile decomposition
spatial_decomposition — every group's decomposition (supplementary JSON)

Each function takes the output of analysis._data.load_all_seeds() and
returns a list of dicts (one per row) in addition to printing to stdout.
"""
import numpy as np
from scipy import stats as scipy_stats

from ._data import _decompose_seed
from ._stats_helpers import cliffs_delta, holm_bonferroni


def table_main_results(groups, min_seeds=10):
    """Print Table 2 from the paper: all groups with key metrics.

    Returns:
        list of dicts for each row.
    """
    rows = []
    print(f"{'n':>4} {'β':>3} {'Seeds':>5} {'Mean Δd(LN)':>11} {'Std':>7} "
          f"{'Win%':>5} {'β/n':>5}")
    print("-" * 50)

    for (n, beta), seeds in sorted(groups.items()):
        if len(seeds) < min_seeds:
            continue
        advs = np.array([s["advantage"] for s in seeds])
        row = {
            "n": n, "beta": beta, "seeds": len(seeds),
            "mean": float(np.mean(advs)),
            "std": float(np.std(advs, ddof=1)),
            "win_rate": float(np.mean(advs > 0) * 100),
            "beta_n": beta / n,
        }
        rows.append(row)
        print(f"{n:>4} {beta:>3} {len(seeds):>5} {row['mean']:>+11.4f} "
              f"{row['std']:>7.4f} {row['win_rate']:>5.1f} {row['beta_n']:>5.2f}")

    return rows


def table_statistics(groups, min_seeds=10):
    """Print Table 3: CIs, Cohen's d, Cliff's δ, raw + Holm-adjusted p-values.

    Holm-Bonferroni correction is applied across the rendered row set
    (one family for the t-test column, one for the Wilcoxon column) so
    the family-wise error rate is bounded at the conventional 0.05
    threshold for the entire table.

    Returns:
        list of dicts for each row.
    """
    eligible = [
        (n, beta, seeds) for (n, beta), seeds in sorted(groups.items())
        if len(seeds) >= min_seeds
    ]

    raw_rows: list[dict] = []
    for n, beta, seeds in eligible:
        advs = np.array([s["advantage"] for s in seeds])
        std = np.std(advs, ddof=1)
        se = std / np.sqrt(len(advs))
        t_crit = scipy_stats.t.ppf(0.975, df=len(advs) - 1)
        ci_lo = np.mean(advs) - t_crit * se
        ci_hi = np.mean(advs) + t_crit * se
        d = np.mean(advs) / std if std > 0 else 0
        delta = cliffs_delta(advs)
        _, p_t = scipy_stats.ttest_1samp(advs, 0)
        try:
            _, p_w = scipy_stats.wilcoxon(advs)
        except Exception:
            p_w = None
        raw_rows.append({
            "n": n, "beta": beta,
            "ci_lo": float(ci_lo), "ci_hi": float(ci_hi),
            "cohens_d": float(d),
            "cliffs_delta": float(delta),
            "p_ttest": float(p_t),
            "p_wilcoxon": float(p_w) if p_w is not None else None,
        })

    p_ttest_holm = holm_bonferroni([r["p_ttest"] for r in raw_rows])
    p_wilcoxon_holm = holm_bonferroni([r["p_wilcoxon"] for r in raw_rows])
    for row, p_t_h, p_w_h in zip(raw_rows, p_ttest_holm, p_wilcoxon_holm, strict=False):
        row["p_ttest_holm"] = float(p_t_h) if p_t_h is not None else None
        row["p_wilcoxon_holm"] = (
            float(p_w_h) if p_w_h is not None else None
        )

    def _fmt_p(p):
        if p is None: return "N/A"
        if p < 1e-50: return "< 1e-50"
        if p < 1e-20: return "< 1e-20"
        if p < 1e-10: return "< 1e-10"
        return f"{p:.2e}"

    print(f"{'n':>4} {'β':>3} {'95% CI':>18} {'Cohen d':>8} {'Cliff δ':>8} "
          f"{'t-test p':>12} {'t Holm p':>12} {'Wilcox p':>12} {'W Holm p':>12}")
    print("-" * 110)
    for row in raw_rows:
        print(
            f"{row['n']:>4} {row['beta']:>3} "
            f"[{row['ci_lo']:.3f}, {row['ci_hi']:.3f}]   "
            f"{row['cohens_d']:>8.2f} {row['cliffs_delta']:>+8.3f} "
            f"{_fmt_p(row['p_ttest']):>12} {_fmt_p(row['p_ttest_holm']):>12} "
            f"{_fmt_p(row['p_wilcoxon']):>12} "
            f"{_fmt_p(row['p_wilcoxon_holm']):>12}"
        )

    return raw_rows


def spatial_decomposition(groups, min_seeds=10):
    """Head/mid/tail decomposition for every group (results/profile_decomposition.json).

    Means are signed nats (positive = SD-BKZ closer to the fixed point). The
    pct_* shares are |region| / (|head| + |mid| + |tail|), so they stay
    meaningful in groups where BKZ wins; largest_region is the region with
    the largest |mean|. Win rates are the share of seeds where the region's
    mean improvement is positive.
    """
    out = []
    for (n, beta), seeds in sorted(groups.items()):
        if len(seeds) < min_seeds:
            continue
        rows = [d for d in (_decompose_seed(s) for s in seeds) if d is not None]
        if not rows:
            continue
        a = np.array(rows)
        means = np.array([np.mean([r[i] for r in rows]) for i in range(3)])
        mag = np.abs(means)
        rec = {"n": n, "beta": beta, "num_seeds": len(rows)}
        for i, region in enumerate(("head", "mid", "tail")):
            rec[f"mean_{region}_improvement"] = float(means[i])
        for i, region in enumerate(("head", "mid", "tail")):
            rec[f"pct_{region}"] = float(mag[i] / mag.sum() * 100)
        for i, region in enumerate(("head", "mid", "tail")):
            rec[f"{region}_win_rate"] = float((a[:, i] > 0).mean() * 100)
        rec["largest_region"] = ("HEAD", "MID", "TAIL")[int(mag.argmax())]
        out.append(rec)
    return out


def table_spatial(groups, min_seeds=10):
    """Print Table 4 from the paper: profile decomposition percentages.

    Returns:
        list of dicts for each row.
    """
    rows = []
    print(f"{'n':>4} {'β':>3} {'Seeds':>5} {'Head%':>6} {'Mid%':>6} "
          f"{'Tail%':>6} {'Mid WR':>7}")
    print("-" * 45)

    for g in spatial_decomposition(groups, min_seeds=min_seeds):
        h = g["mean_head_improvement"]
        m = g["mean_mid_improvement"]
        t = g["mean_tail_improvement"]
        total = h + m + t
        # Skip groups where a signed share is meaningless: BKZ wins overall,
        # or one region outweighs the total (shares above 100% or negative).
        if total <= 0 or max(abs(h), abs(m), abs(t)) > total:
            continue

        n, beta = g["n"], g["beta"]
        row = {
            "n": n, "beta": beta, "seeds": g["num_seeds"],
            "head_pct": float(h / total * 100), "mid_pct": float(m / total * 100),
            "tail_pct": float(t / total * 100), "mid_win_rate": g["mid_win_rate"],
        }
        rows.append(row)
        print(f"{n:>4} {beta:>3} {row['seeds']:>5} {row['head_pct']:>5.0f}% "
              f"{row['mid_pct']:>5.0f}% {row['tail_pct']:>5.0f}% {row['mid_win_rate']:>6.0f}%")

    return rows
