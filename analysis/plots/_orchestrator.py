"""Run the full figure pipeline + diagnostics + tables.

This is the entry point used by `analysis/paper_figures.py` and is also
importable as `analysis.plots.generate_all` for callers that want the
whole pipeline programmatically.
"""
import os

from .. import diagnostics, tables
from .._data import load_3x_tour_data, load_all_seeds
from .absolute_dln import fig_absolute_dln
from .advantage_histograms import fig_advantage_histograms
from .basis_profiles import fig_basis_profiles
from .beta_n_scatter import fig_beta_n_scatter
from .convergence_500_tours import fig_convergence_500_tours
from .convergence_trajectories import fig_convergence_trajectories
from .dimension_scaling import fig_dimension_scaling
from .dln_vs_rhf import fig_dln_vs_rhf
from .gso_profiles import fig_gso_profiles
from .peak_dip_trajectory import fig_peak_dip_trajectory
from .per_position_landscape import fig_per_position_landscape
from .q3329_degeneracy import fig_q3329_degeneracy
from .spatial_decomposition import fig_spatial_decomposition
from .tour_test_3x import fig_3x_tour_test


def generate_all(
    results_dirs=None,
    output_dir=None,
    tour_dir=None,
    min_seeds=10,
    campaign=None,
    tour_campaign=None,
):
    """Run all figures and diagnostics.

    Dual-mode seed load:
      - campaign=<name>           manifest query (preferred, v1.3+)
      - results_dirs=[dir, ...]   legacy globber fallback

    Args:
        results_dirs: List of directories containing seed JSONs (legacy
            mode). Ignored when `campaign` is set.
        output_dir: Where to save PNGs and text output.
        tour_dir: Path to a 3x-tour directory (legacy). Ignored when
            `tour_campaign` is set.
        min_seeds: Minimum seeds per group.
        campaign: Manifest campaign name for the main figure pipeline
            (e.g. "main"). Preferred path post-v1.3.
        tour_campaign: Manifest campaign name for the 3x-tour figure
            (e.g. "tours3x").
    """
    os.makedirs(output_dir, exist_ok=True)
    if campaign:
        groups = load_all_seeds(campaign=campaign, min_seeds=1)
    else:
        groups = load_all_seeds(*(results_dirs or []), min_seeds=1)

    if not groups:
        if campaign:
            print(f"No data found for campaign={campaign!r} — check "
                  "results/seed_manifest.json.")
        else:
            print("No data found. Check your --results-dir paths.")
        return

    print(f"\nGenerating figures (min_seeds={min_seeds})...")
    print()

    print("--- Dimension scaling ---")
    fig_dimension_scaling(groups, output_dir, min_seeds=min_seeds)

    print("--- Advantage histograms ---")
    fig_advantage_histograms(groups, output_dir, min_seeds=max(20, min_seeds))

    print("--- Convergence trajectories ---")
    fig_convergence_trajectories(groups, output_dir)

    if tour_campaign or tour_dir:
        print("--- 3x tour test ---")
        # load_3x_tour_data has its own dual-mode: passing tour_dir=None
        # triggers the manifest path (campaign="tours3x" by default).
        tour_seeds = load_3x_tour_data(tour_dir)
        fig_3x_tour_test(tour_seeds, output_dir)

    print("--- Spatial decomposition ---")
    fig_spatial_decomposition(groups, output_dir, min_seeds=min_seeds)

    print("--- Absolute d(LN) ---")
    fig_absolute_dln(groups, output_dir, min_seeds=min_seeds)

    print("--- β/n scatter ---")
    fig_beta_n_scatter(groups, output_dir, min_seeds=min_seeds)

    print("--- d(LN) vs RHF ---")
    # Uses same min_seeds as dimension_scaling so both figures describe
    # the same set of groups. Previously hardcoded to max(50, ...), which
    # would silently drop groups that the hero curve included.
    fig_dln_vs_rhf(groups, output_dir, min_seeds=min_seeds)

    print("--- Basis profiles ---")
    fig_basis_profiles(groups, output_dir)

    print("--- GSO log-norm profiles ---")
    fig_gso_profiles(groups, output_dir)

    print("--- 500-tour convergence (n=90 + n=140) ---")
    fig_convergence_500_tours(output_dir)

    print("--- q=3329 degeneracy ---")
    fig_q3329_degeneracy(groups, output_dir)

    print("--- Per-position landscape ---")
    fig_per_position_landscape(groups, output_dir, min_seeds=min_seeds)

    print("--- Peak/dip trajectory ---")
    fig_peak_dip_trajectory(groups, output_dir, min_seeds=min_seeds)

    print("\n--- Diagnostics ---")
    print("\n[Distribution diagnostics]")
    diagnostics.diag_distribution(groups)

    print("\n[Crossover tours]")
    diagnostics.diag_crossover_tours(groups)

    print("\n[Runtime overhead]")
    diagnostics.diag_runtime_overhead(groups)

    print("\n[n=90 deep dive]")
    diagnostics.diag_n90_deep_dive(groups)

    print("\n--- Tables ---")
    print("\n[Table 2: Main results]")
    tables.table_main_results(groups, min_seeds=min_seeds)

    print("\n[Table 3: Statistics]")
    tables.table_statistics(groups, min_seeds=min_seeds)

    print("\n[Table 4: Spatial decomposition]")
    tables.table_spatial(groups, min_seeds=min_seeds)

    print(f"\nDone. Figures saved to: {output_dir}")
