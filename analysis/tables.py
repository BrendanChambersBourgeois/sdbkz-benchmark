"""Paper-ready text tables for the SD-BKZ benchmark.

table_main_results — Table 2: per-group means, std, win rate, β/n
table_statistics   — Table 3: 95% CIs, Cohen's d, t-test/Wilcoxon p-values
table_spatial      — Table 4: head/mid/tail Rankin profile decomposition

Each function takes the output of analysis._data.load_all_seeds() and
returns a list of dicts (one per row) in addition to printing to stdout.
"""
import numpy as np
from scipy import stats as scipy_stats

from ._data import _decompose_seed


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
    """Print Table 3 from the paper: CIs, Cohen's d, p-values.

    Returns:
        list of dicts for each row.
    """
    rows = []
    print(f"{'n':>4} {'β':>3} {'95% CI':>18} {'Cohen d':>8} "
          f"{'t-test p':>12} {'Wilcoxon p':>12}")
    print("-" * 65)

    for (n, beta), seeds in sorted(groups.items()):
        if len(seeds) < min_seeds:
            continue
        advs = np.array([s["advantage"] for s in seeds])
        se = np.std(advs, ddof=1) / np.sqrt(len(advs))
        t_crit = scipy_stats.t.ppf(0.975, df=len(advs) - 1)
        ci_lo = np.mean(advs) - t_crit * se
        ci_hi = np.mean(advs) + t_crit * se
        d = np.mean(advs) / np.std(advs, ddof=1) if np.std(advs, ddof=1) > 0 else 0
        _, p_t = scipy_stats.ttest_1samp(advs, 0)
        try:
            _, p_w = scipy_stats.wilcoxon(advs, alternative="greater")
        except Exception:
            p_w = None

        def _fmt_p(p):
            if p is None: return "N/A"
            if p < 1e-50: return "< 1e-50"
            if p < 1e-20: return "< 1e-20"
            if p < 1e-10: return "< 1e-10"
            return f"{p:.2e}"

        row = {
            "n": n, "beta": beta,
            "ci_lo": float(ci_lo), "ci_hi": float(ci_hi),
            "cohens_d": float(d),
            "p_ttest": float(p_t),
            "p_wilcoxon": float(p_w) if p_w is not None else None,
        }
        rows.append(row)
        print(f"{n:>4} {beta:>3} [{ci_lo:.3f}, {ci_hi:.3f}]   "
              f"{d:>8.2f} {_fmt_p(p_t):>12} {_fmt_p(p_w):>12}")

    return rows


def table_spatial(groups, min_seeds=10):
    """Print Table 4 from the paper: profile decomposition percentages.

    Returns:
        list of dicts for each row.
    """
    rows = []
    print(f"{'n':>4} {'β':>3} {'Seeds':>5} {'Head%':>6} {'Mid%':>6} "
          f"{'Tail%':>6} {'Mid WR':>7}")
    print("-" * 45)

    for (n, beta), seeds in sorted(groups.items()):
        if len(seeds) < min_seeds:
            continue

        heads, mids, tails = [], [], []
        mid_wins = 0
        total_decomposed = 0
        for s in seeds:
            decomp = _decompose_seed(s)
            if decomp is None:
                continue
            heads.append(decomp[0])
            mids.append(decomp[1])
            tails.append(decomp[2])
            if decomp[1] > 0:
                mid_wins += 1
            total_decomposed += 1

        if not heads:
            continue

        h, m, t = np.mean(heads), np.mean(mids), np.mean(tails)
        total = h + m + t
        # Skip groups where the percentage representation is meaningless:
        # - total is non-positive (BKZ wins overall)
        # - any component magnitude exceeds the total (sign-flip groups
        #   produce >100% / negative percentages that don't reflect a
        #   sensible "share" of improvement).
        if total <= 0 or max(abs(h), abs(m), abs(t)) > total:
            continue

        h_pct = np.mean(heads) / total * 100
        m_pct = np.mean(mids) / total * 100
        t_pct = np.mean(tails) / total * 100
        m_wr = mid_wins / total_decomposed * 100

        row = {
            "n": n, "beta": beta, "seeds": total_decomposed,
            "head_pct": float(h_pct), "mid_pct": float(m_pct),
            "tail_pct": float(t_pct), "mid_win_rate": float(m_wr),
        }
        rows.append(row)
        print(f"{n:>4} {beta:>3} {total_decomposed:>5} {h_pct:>5.0f}% "
              f"{m_pct:>5.0f}% {t_pct:>5.0f}% {m_wr:>6.0f}%")

    return rows
