# Examples

Self-contained scripts you can run in under 30 seconds to see the benchmark in action. They use existing result files in `results/` — no new computation needed.

| Script | What it does | Runtime |
|---|---|---|
| `01_inspect_one_seed.py` | Pretty-prints one (n, β, seed) result | <1s |
| `02_compare_two_groups.py` | Statistical comparison of two groups | ~2s |
| `03_plot_basis_profile.py` | GSO log-norm chart for one seed | ~2s |

All three default to **n=100, β=30, seed=1** — the peak group from the paper.

## Run them

```bash
# Inspect one seed
python3 examples/01_inspect_one_seed.py
python3 examples/01_inspect_one_seed.py --n 150 --beta 30 --seed 5

# Compare two groups
python3 examples/02_compare_two_groups.py
python3 examples/02_compare_two_groups.py --group1 100 30 --group2 150 30

# Plot basis profile (saves PNG to examples/output/)
python3 examples/03_plot_basis_profile.py
python3 examples/03_plot_basis_profile.py --n 70 --beta 20 --seed 1
```

## What each example demonstrates

**01 (inspect)** — Shows what's in a single result file: BKZ vs SD-BKZ d(LN), runtime, RHF, dimension, precision. Good first glance to see the data shape.

**02 (compare)** — The simplest possible cross-group analysis. Computes mean, median, std, win rate, and Cohen's d for two groups and prints the difference. This is what `analysis/stats_analysis.py` does for *all* groups; here it's just two.

**03 (profile)** — Generates a single-seed version of fig10 (GSO log-norm staircase with GSA + Li-Nguyen predictions). Useful for seeing the head concavity and tail collapse on a per-seed basis instead of averaged across 100 seeds.

After running these you'll understand the data layout well enough to read `analysis/stats_analysis.py` and `analysis/paper_figures.py` without much friction.
