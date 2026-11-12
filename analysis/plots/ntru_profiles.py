"""Paper 2, figure: raw Gram-Schmidt profiles across the DSD onset.

One key (n=113, beta=20, fplll, 50 tours) at three moduli: below both onsets,
between the SD-BKZ and BKZ onsets, above both (tab:dsdgap). Final
log||b_i*|| for BKZ and SD-BKZ over the initial profile. The seed is the
lowest one where, at the middle modulus, SD-BKZ meets the two-part DSD
criterion and BKZ does not. No curated constants beyond the three moduli.
"""
import glob
import json
import math
import os
import sys

import matplotlib.pyplot as plt

from .._style import COLORS

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.path.join(_REPO, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO, "scripts"))
from extract_dsd_onset import _is_dsd, _seed_is_poisoned  # noqa: E402

N, BETA = 113, 20
QS = [613, 859, 1163]     # below both onsets / between / above both
LABELS = ["below both onsets", "between the onsets", "above both onsets"]


def _cell(q):
    pat = os.path.join(_REPO, "results", "seeds", "ntru", f"q{q}", "p*_mt50",
                       f"n{N:03d}_beta{BETA:02d}", "seed*.json")
    out = {}
    for f in sorted(glob.glob(pat)):
        with open(f) as fh:
            d = json.load(fh)
        out[d["seed"]] = d
    return out


def _pick(cells):
    """Lowest seed present and clean at every q, SD-only DSD at the middle q."""
    for s, d in sorted(cells[1].items()):
        if not all(s in c for c in cells):
            continue
        if any(_seed_is_poisoned(c[s], v) for c in cells for v in ("bkz", "sdbkz")):
            continue
        if _is_dsd(d, "sdbkz", N) and not _is_dsd(d, "bkz", N):
            return s
    raise SystemExit("ntru_profiles: no seed with SD-only DSD at the middle q")


def fig_ntru_profiles(output_dir=".", fname="profiles.png"):
    sd_c, bkz_c = COLORS["sdbkz"], COLORS["bkz"]
    cells = [_cell(q) for q in QS]
    seed = _pick(cells)
    secret = math.log(math.sqrt(2 * N * 2 / 3))
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), sharey=True)
    for ax, q, lbl, c in zip(axes, QS, LABELS, cells, strict=True):
        d = c[seed]
        ax.plot(d["initial_gs_lognorms"], color="#94a3b8", lw=1.2, ls=":",
                label="initial profile", zorder=2)
        ax.plot(d["gs_lognorms_bkz"], color=bkz_c, lw=1.6, label="BKZ", zorder=3)
        ax.plot(d["gs_lognorms_sdbkz"], color=sd_c, lw=1.6, label="SD-BKZ", zorder=4)
        ax.axhline(secret, color=COLORS["zero"], lw=1.0, ls="--", alpha=0.7,
                   zorder=1, label=r"secret $\log\|(f,g)\|$")
        ax.axvline(N, color="#475569", lw=0.8, ls="--", alpha=0.6, zorder=1)
        ax.set_title(f"$q={q}$: {lbl}")
        ax.set_xlabel("GS position $i$")
        ax.grid(alpha=0.15, zorder=0)
    axes[0].set_ylabel(r"$\log\|\mathbf{b}_i^*\|$")
    axes[0].legend(loc="lower left", framealpha=0.9, fontsize=9)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out, seed
