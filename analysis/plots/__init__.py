"""Figure modules for the SD-BKZ benchmark.

One module per figure plus _orchestrator for the full pipeline. Each
fig_* function is independently callable; pass the output of
analysis._data.load_all_seeds() and an output directory. Module names
describe figure content, not position in the paper — paper figure
numbering is assigned by the paper itself via captions or LaTeX
\\ref, so reorderings don't require renaming anything here.

Example:
    from analysis._data import load_all_seeds
    from analysis.plots import fig_dimension_scaling, generate_all

    groups = load_all_seeds("/path/to/results/raw", "/path/to/results/cloud")
    fig_dimension_scaling(groups, output_dir="./figures")

    # Or run everything:
    generate_all(["/path/to/results/raw"], "./figures")
"""
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
from ._orchestrator import generate_all

__all__ = [
    "fig_dimension_scaling",
    "fig_advantage_histograms",
    "fig_convergence_trajectories",
    "fig_spatial_decomposition",
    "fig_absolute_dln",
    "fig_beta_n_scatter",
    "fig_3x_tour_test",
    "fig_dln_vs_rhf",
    "fig_basis_profiles",
    "fig_gso_profiles",
    "fig_convergence_500_tours",
    "fig_q3329_degeneracy",
    "generate_all",
]
