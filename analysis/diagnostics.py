"""Statistical diagnostics for the SD-BKZ benchmark.

Print-style diagnostics that complement the figures: distribution shape
(normality, skewness, kurtosis), crossover tour statistics, runtime
overhead, and a deep-dive on the n=90 peak.

Each function takes the output of analysis._data.load_all_seeds() and
returns a dict of results in addition to printing to stdout.
"""
import numpy as np
from scipy import stats as scipy_stats


def diag_distribution(groups, target_n=None, target_beta=None):
    """Print distribution diagnostics for one or all groups.

    Covers: normality (Shapiro-Wilk), skewness, kurtosis, bimodality
    (Hartigan's dip test approximation via percentiles).

    Args:
        groups: Output of load_all_seeds().
        target_n: Filter to specific n (None = all).
        target_beta: Filter to specific beta (None = all).

    Returns:
        dict of diagnostics per group.
    """
    results = {}
    for (n, beta), seeds in sorted(groups.items()):
        if target_n is not None and n != target_n:
            continue
        if target_beta is not None and beta != target_beta:
            continue
        if len(seeds) < 10:
            continue

        advs = np.array([s["advantage"] for s in seeds])
        sw_stat, sw_p = scipy_stats.shapiro(advs)
        skew = scipy_stats.skew(advs)
        kurt = scipy_stats.kurtosis(advs)
        p5, p25, p50, p75, p95 = np.percentile(advs, [5, 25, 50, 75, 95])

        # Losses analysis
        losses = advs[advs < 0]
        wins = advs[advs > 0]

        diag = {
            "n": n, "beta": beta, "seeds": len(seeds),
            "mean": float(np.mean(advs)),
            "median": float(p50),
            "std": float(np.std(advs, ddof=1)),
            "skewness": float(skew),
            "kurtosis": float(kurt),
            "shapiro_w": float(sw_stat),
            "shapiro_p": float(sw_p),
            "normal": sw_p > 0.05,
            "p5": float(p5), "p25": float(p25), "p50": float(p50),
            "p75": float(p75), "p95": float(p95),
            "n_losses": len(losses),
            "mean_loss": float(np.mean(losses)) if len(losses) > 0 else None,
            "n_wins": len(wins),
            "mean_win": float(np.mean(wins)) if len(wins) > 0 else None,
        }
        results[(n, beta)] = diag

        print(f"n={n:>3} β={beta:>2} | {len(seeds):>3} seeds | "
              f"mean={np.mean(advs):+.3f} med={p50:+.3f} | "
              f"skew={skew:+.2f} kurt={kurt:+.2f} | "
              f"Shapiro p={sw_p:.3f} ({'normal' if sw_p > 0.05 else 'NON-NORMAL'}) | "
              f"losses={len(losses)} (mean {np.mean(losses):.3f})" if len(losses) > 0 else
              f"n={n:>3} β={beta:>2} | {len(seeds):>3} seeds | "
              f"mean={np.mean(advs):+.3f} med={p50:+.3f} | "
              f"skew={skew:+.2f} kurt={kurt:+.2f} | "
              f"Shapiro p={sw_p:.3f} ({'normal' if sw_p > 0.05 else 'NON-NORMAL'}) | "
              f"losses=0")

    return results


def diag_crossover_tours(groups):
    """Compute crossover tour statistics per group.

    The crossover tour is when SD-BKZ's d(LN) first drops below BKZ's
    final d(LN).

    Returns:
        dict of {(n, beta): {mean, std, min, max, median}}.
    """
    results = {}
    print(f"{'Group':<16} {'Seeds':>5} {'Mean':>6} {'Std':>6} "
          f"{'Min':>4} {'Med':>5} {'Max':>4}")
    print("-" * 55)

    for (n, beta), seeds in sorted(groups.items()):
        crossovers = [s["crossover_tour"] for s in seeds
                      if s.get("crossover_tour") is not None]
        if not crossovers:
            continue
        c = np.array(crossovers)
        results[(n, beta)] = {
            "mean": float(np.mean(c)),
            "std": float(np.std(c, ddof=1)) if len(c) > 1 else 0,
            "min": int(np.min(c)),
            "max": int(np.max(c)),
            "median": float(np.median(c)),
            "count": len(c),
        }
        print(f"n={n:>3} β={beta:>2}     {len(c):>5} {np.mean(c):>6.1f} "
              f"{np.std(c, ddof=1):>6.1f} {np.min(c):>4} {np.median(c):>5.0f} "
              f"{np.max(c):>4}")

    return results


def diag_runtime_overhead(groups):
    """Compute actual SD-BKZ/BKZ runtime ratio per group.

    Returns:
        dict of {(n, beta): {mean_ratio, std_ratio, ...}}.
    """
    results = {}
    print(f"{'Group':<16} {'Seeds':>5} {'Mean ratio':>10} {'Std':>6} "
          f"{'BKZ (s)':>8} {'SD-BKZ (s)':>10}")
    print("-" * 60)

    for (n, beta), seeds in sorted(groups.items()):
        ratios = []
        bkz_times = []
        sd_times = []
        for s in seeds:
            bt = s.get("bkz_time")
            st = s.get("sdbkz_time")
            if bt and st and bt > 0:
                ratios.append(st / bt)
                bkz_times.append(bt)
                sd_times.append(st)
        if not ratios:
            continue
        r = np.array(ratios)
        results[(n, beta)] = {
            "mean_ratio": float(np.mean(r)),
            "std_ratio": float(np.std(r, ddof=1)) if len(r) > 1 else 0,
            "mean_bkz_time": float(np.mean(bkz_times)),
            "mean_sdbkz_time": float(np.mean(sd_times)),
            "count": len(ratios),
        }
        print(f"n={n:>3} β={beta:>2}     {len(ratios):>5} {np.mean(r):>10.2f}x "
              f"{np.std(r, ddof=1):>6.2f} {np.mean(bkz_times):>8.0f} "
              f"{np.mean(sd_times):>10.0f}")

    return results


def diag_n90_deep_dive(groups):
    """Detailed analysis of the n=90 peak: distribution, absolute d(LN),
    comparison with adjacent dimensions.

    Returns:
        dict with analysis results.
    """
    results = {}
    print("=" * 70)
    print("n=90 DEEP DIVE")
    print("=" * 70)

    for beta in [20, 30, 40]:
        key = (90, beta)
        if key not in groups:
            continue
        seeds = groups[key]
        advs = np.array([s["advantage"] for s in seeds])
        bkz_dlns = np.array([s["bkz_final_dln"] for s in seeds
                              if "bkz_final_dln" in s])
        sd_dlns = np.array([s["sdbkz_final_dln"] for s in seeds
                             if "sdbkz_final_dln" in s])

        print(f"\nn=90, β={beta} ({len(seeds)} seeds):")
        print(f"  Advantage: mean={np.mean(advs):.4f}, "
              f"std={np.std(advs, ddof=1):.4f}, "
              f"min={np.min(advs):.4f}, max={np.max(advs):.4f}")
        print(f"  BKZ d(LN):    mean={np.mean(bkz_dlns):.4f}, "
              f"std={np.std(bkz_dlns, ddof=1):.4f}")
        print(f"  SD-BKZ d(LN): mean={np.mean(sd_dlns):.4f}, "
              f"std={np.std(sd_dlns, ddof=1):.4f}")

        for adj_n in [80, 100]:
            adj_key = (adj_n, beta)
            if adj_key in groups:
                adj_seeds = groups[adj_key]
                adj_advs = np.array([s["advantage"] for s in adj_seeds])
                adj_bkz = np.array([s["bkz_final_dln"] for s in adj_seeds
                                     if "bkz_final_dln" in s])
                pct_change = (np.mean(advs) - np.mean(adj_advs)) / abs(np.mean(adj_advs)) * 100
                print(f"  vs n={adj_n}: adv={np.mean(adj_advs):.4f}, "
                      f"change={pct_change:+.0f}%, "
                      f"abs_bkz_dln={np.mean(adj_bkz):.4f}")

        results[beta] = {
            "mean_advantage": float(np.mean(advs)),
            "mean_bkz_dln": float(np.mean(bkz_dlns)),
            "mean_sdbkz_dln": float(np.mean(sd_dlns)),
            "advantage_relative_to_bkz": float(np.mean(advs) / np.mean(bkz_dlns)),
        }

    return results
