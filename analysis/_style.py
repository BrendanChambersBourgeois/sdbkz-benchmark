"""Shared matplotlib style and color palette for the SD-BKZ benchmark figures.

Imported by every figure module so the visual identity stays consistent
across the paper. The Agg backend is set in analysis/__init__.py before
this module loads, so importing matplotlib.pyplot here is safe.
"""
import matplotlib.pyplot as plt


COLORS = {
    "beta20": "#0891b2",   # cyan-600
    "beta30": "#ea580c",   # orange-600
    "beta40": "#9333ea",   # purple-600
    "bkz":    "#000000",   # black
    "sdbkz":  "#15803d",   # green-700 (deeper, more saturated)
    "head":   "#0891b2",
    "mid":    "#ea580c",
    "tail":   "#9333ea",
    "zero":   "#dc2626",   # red-600
    "grid":   "#e2e8f0",
}

BETA_LABELS = {20: "β = 20", 30: "β = 30", 40: "β = 40"}
BETA_COLORS = {20: COLORS["beta20"], 30: COLORS["beta30"], 40: COLORS["beta40"]}
BETA_MARKERS = {20: "o", 30: "s", 40: "D"}


def _apply_style():
    """Apply consistent matplotlib rcParams for all figures.

    Called once from analysis/__init__.py at package import time. Safe to
    call again — overrides existing rcParams idempotently.
    """
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.grid": True,
        "axes.grid.which": "major",
        "grid.alpha": 0.3,
        "grid.linewidth": 0.5,
        "font.family": "serif",
        "font.size": 11,
        "axes.labelsize": 12,
        "axes.titlesize": 13,
        "legend.fontsize": 10,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.1,
    })
