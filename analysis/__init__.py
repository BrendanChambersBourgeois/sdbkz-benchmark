"""SD-BKZ benchmark analysis package.

Generates publication-quality figures, diagnostics, and tables from the
per-seed JSON files produced by the sweep scripts. Reads-only — safe to
run while experiments are in progress.

Top-level entry points:
    analysis.plots.generate_all()       — Run the full figure pipeline
    analysis.plots.fig_dimension_scaling()  (and other fig_* functions)
    analysis.diagnostics.diag_*()       — Statistical diagnostics
    analysis.tables.table_*()           — Paper-ready text tables

Standalone CLI:
    python3 analysis/paper_figures.py --help

The matplotlib Agg backend is set at import time so headless invocation
works without an X server. Plot styling is applied via _apply_style().
"""
import matplotlib

matplotlib.use("Agg")
from ._style import _apply_style

_apply_style()
