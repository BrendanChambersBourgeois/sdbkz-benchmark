#!/usr/bin/env python3
"""
Convergence test extension: n=90, β=30, 1000 tours, 20 seeds.

Paper §5.3 convergence story rests on 500-tour data at n=90 (SD-BKZ
keeps improving through tour 500, BKZ plateaus by tour 70). Open
question: does SD-BKZ plateau between tour 500 and 1000, or keep
descending? This run extends the tour budget 2× and answers directly.

Distinct seed-path slot from the 500-tour baseline via max_tours=1000:
- 500-tour data : results/seeds/convergence/q97/n090_beta30_mt500/
- 1000-tour run : results/seeds/convergence/q97/n090_beta30_mt1000/

Legacy summary file name collides (same `OUTPUT_DIR`). Rename after
run if both summaries needed.

Field-name quirk: the inherited runner writes
`bkz_improvement_70_to_500` / `sdbkz_improvement_70_to_500` — for
this 1000-tour run those are actually `70_to_final_tour_1000`
deltas (the index is `[69]` vs `[-1]`, which resolves to `[999]`
here). Canonical data = `bkz_dln_per_tour` / `sdbkz_dln_per_tour`
arrays with 1000 entries each. Any downstream analysis should
compute improvements off those arrays, not the misnamed scalars.

Usage:
    nohup python3 scripts/run_convergence_n90_mt1000.py \
        > logs/convergence_n90_mt1000_stdout.log 2>&1 &
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import run_convergence_test

run_convergence_test.N = 90
run_convergence_test.BETA = 30
run_convergence_test.MAX_TOURS = 1000
# NUM_WORKERS = 22 and NUM_SEEDS = 20 inherited from the base module

run_convergence_test.main()
