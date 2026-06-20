"""Paper 2, Figure: per-position SD-BKZ vs BKZ profile difference (n=89, beta=40).

Per-position log||b*_i||_SD - log||b*_i||_BKZ averaged over seeds, one curve per
modulus q, faceted by oracle (fplll enumeration | G6K sieve). Reproduces the
head-down/tail-up redistribution of Section 6: SD-BKZ pulls mass head-down and
pushes it tail-up in the pre-onset band (q in [127,157]), peaking in the last
few GS vectors, and is flat in the onset regime (q >= 181); both engines agree.
This is the committed module for the figure formerly rendered from the
plots_findings artifact -- closes the repro gap (one module per figure).

Reads gs_lognorms_bkz / gs_lognorms_sdbkz from the per-seed JSONs directly
(results/seeds/{ntru,ntru_g6k}/q*/.../n089_beta40/); no curated constants, no RNG.
"""
import glob
import json
import os

import matplotlib.pyplot as plt
import numpy as np

# Representative q-sweep present on BOTH engines at n=89, beta=40: control (97),
# pre-onset band (127-157), onset regime (181, 211).
QS = [97, 127, 137, 149, 157, 181, 211]
ENGINES = [("fplll (enum)", "ntru"), ("G6K (sieve)", "ntru_g6k")]
N, BETA = 89, 40


def _per_position_mean(tag, q):
    """Mean over seeds of (gs_lognorms_sdbkz - gs_lognorms_bkz) per position."""
    paths = [p for p in glob.glob(
        f"results/seeds/{tag}/q{q}/*/n{N:03d}_beta{BETA}/seed*.json")
        if "_fat" not in p]
    diffs = []
    for p in paths:
        d = json.load(open(p))
        if "gs_lognorms_bkz" in d and "gs_lognorms_sdbkz" in d:
            bkz = np.asarray(d["gs_lognorms_bkz"], dtype=float)
            sd = np.asarray(d["gs_lognorms_sdbkz"], dtype=float)
            if bkz.shape == sd.shape:
                diffs.append(sd - bkz)
    if not diffs:
        return None, 0
    return np.mean(np.vstack(diffs), axis=0), len(diffs)


def fig_ntru_per_position(output_dir=".", fname="per_position_attribution.png"):
    """Faceted per-position SD-BKZ vs BKZ profile difference at n=89, beta=40."""
    cmap = plt.get_cmap("viridis")
    qmin, qmax = min(QS), max(QS)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)

    for ax, (label, tag) in zip(axes, ENGINES, strict=True):
        xmax = 0
        for q in QS:
            mean_diff, nseed = _per_position_mean(tag, q)
            if mean_diff is None:
                continue
            xmax = max(xmax, len(mean_diff) - 1)
            frac = (q - qmin) / (qmax - qmin) if qmax > qmin else 0.5
            ax.plot(np.arange(len(mean_diff)), mean_diff, color=cmap(frac),
                    linewidth=1.7, label=f"$q={q}$")
        ax.axhline(0.0, color="#dc2626", linewidth=0.9, linestyle="--", alpha=0.6)
        # i=n divider: the profile is the 2n-dim NTRU basis, so the abrupt step
        # at i=N is the q-vector / dual-block boundary, not a plotting artifact.
        # Shade the two halves so the step + tail rise read as structure (the
        # head/tail blocks). Shade only to the data extent (xmax): a literal
        # bound here would blow the x-axis out into empty white space.
        ax.axvspan(0, N, color="#1d4ed8", alpha=0.04, zorder=0)
        ax.axvspan(N, xmax, color="#b45309", alpha=0.05, zorder=0)
        ax.axvline(N, color="#334155", linewidth=1.2, linestyle="--", alpha=0.8)
        # label sits at the TOP of the divider, clear of the lower-left legend
        # (a bottom-anchored box overlaps the legend entries).
        ax.annotate(f"$i={N}$ split", xy=(N, 0.0),
                    xytext=(N + 2, 0.86), fontsize=8.5, color="#1e293b",
                    ha="left", va="top",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white",
                              ec="#94a3b8", alpha=0.85))
        ax.set_title(label)
        ax.set_xlabel("GS position $i$")
        ax.set_xlim(0, xmax)

    # head / tail orientation, shared across panels.
    for ax in axes:
        ax.annotate("head block", xy=(0.02, 0.93), xycoords="axes fraction",
                    fontsize=8.5, color="#1d4ed8", style="italic")
        ax.annotate("tail block", xy=(0.98, 0.93), xycoords="axes fraction",
                    fontsize=8.5, color="#b45309", style="italic", ha="right")
    axes[0].set_ylabel(
        r"$\log\|\mathbf{b}_i^\ast\|_{\mathrm{SD}}-\log\|\mathbf{b}_i^\ast\|_{\mathrm{BKZ}}$"
        "\n(negative $\\Rightarrow$ SD-BKZ shorter here)")
    axes[0].legend(loc="lower left", fontsize=8, ncol=2, framealpha=0.9)
    axes[1].legend(loc="lower left", fontsize=8, ncol=2, framealpha=0.9)
    fig.suptitle(r"Per-position SD-BKZ redistribution ($n=89$, $\beta=40$): "
                 r"head-down / tail-up, both engines", y=1.0)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
