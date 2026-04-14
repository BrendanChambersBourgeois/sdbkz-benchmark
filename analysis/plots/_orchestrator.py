"""Run the full figure pipeline + diagnostics + tables.

This is the entry point used by `analysis/paper_figures.py` and is also
importable as `analysis.plots.generate_all` for callers that want the
whole pipeline programmatically.
"""
import os

from .._data import load_all_seeds, load_3x_tour_data
from .. import diagnostics, tables

from .dimension_scaling import fig_dimension_scaling
from .advantage_histograms import fig_advantage_histograms
from .convergence_trajectories import fig_convergence_trajectories
from .tour_test_3x import fig_3x_tour_test
from .spatial_decomposition import fig_spatial_decomposition
from .absolute_dln import fig_absolute_dln
from .beta_n_scatter import fig_beta_n_scatter
from .dln_vs_rhf import fig_dln_vs_rhf
from .basis_profiles import fig_basis_profiles
from .gso_profiles import fig_gso_profiles
from .convergence_500_tours import fig_convergence_500_tours
from .q3329_degeneracy import fig_q3329_degeneracy


def generate_all(results_dirs, output_dir, tour_dir=None, min_seeds=10):
    """Run all figures and diagnostics.

    Args:
        results_dirs: List of directories containing seed JSONs.
        output_dir: Where to save PNGs and text output.
        tour_dir: Path to results/3x_tours/ (optional).
        min_seeds: Minimum seeds per group.
    """
    os.makedirs(output_dir, exist_ok=True)
    groups = load_all_seeds(*results_dirs, min_seeds=1)

    if not groups:
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

    if tour_dir:
        print("--- 3x tour test ---")
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
