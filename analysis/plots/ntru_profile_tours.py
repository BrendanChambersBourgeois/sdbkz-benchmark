"""Paper 2, figure: Gram-Schmidt profile per tour, BKZ vs SD-BKZ.

The key of the profiles figure (n=113, beta=20, q=859, seed 1) rerun with
per-tour profiles stored (campaign ntru_b2_probe). Colour is log||b_i*|| at
each GS position after each tour: the dense-sublattice collapse appears as
the profile splitting into two flat blocks at i=n.
"""
import json
import os

import matplotlib.pyplot as plt
import numpy as np

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
N = 113
SEED = os.path.join("results", "seeds", "ntru_b2_probe", "q859", "p500_mt50",
                    "n113_beta20", "seed0001.json")


def fig_ntru_profile_tours(output_dir=".", fname="profile_tours.png"):
    with open(os.path.join(_REPO, SEED)) as fh:
        d = json.load(fh)
    mats = [np.array(d[f"{v}_gs_lognorms_per_tour"]).T for v in ("bkz", "sdbkz")]
    lo = min(m.min() for m in mats)
    hi = max(m.max() for m in mats)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), sharey=True)
    for ax, m, lbl in zip(axes, mats, ("BKZ", "SD-BKZ"), strict=True):
        tours = m.shape[1]
        im = ax.imshow(m, aspect="auto", origin="upper", cmap="viridis",
                       vmin=lo, vmax=hi, interpolation="nearest",
                       extent=(0.5, tours + 0.5, m.shape[0], 0))
        ax.axhline(N, color="white", lw=0.8, ls="--", alpha=0.8)
        ax.set_xlim(0.5, 50.5)
        ax.set_title(f"{lbl} ({tours} tours run)")
        ax.set_xlabel("tour")
        ax.grid(False)
    axes[0].set_ylabel("GS position $i$")
    fig.colorbar(im, ax=axes, label=r"$\log\|\mathbf{b}_i^*\|$", pad=0.02)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, fname)
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out
