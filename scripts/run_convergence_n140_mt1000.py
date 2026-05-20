#!/usr/bin/env python3
"""
Convergence test extension: n=140, β=30, 1000 tours, 20 seeds.

Companion to `run_convergence_n90_mt1000.py` — pairs the long-tour
(1000) extension across both convergence regimes characterised in
paper §5.3:

  n=90  1000-tour : tests whether SD-BKZ plateaus past tour 500
                    (it was still improving at 500)
  n=140 1000-tour : tests whether the BKZ→SD-BKZ crossover at
                    convergence survives 2× deeper tour budget
                    (paper §5.3 crossover at full 500-tour was
                    -0.075 nats mean advantage, 4/20 wins)

Distinct seed-path slot from the 500-tour baseline via
max_tours=1000:
- 500-tour data : results/seeds/convergence/q97/n140_beta30_mt500/
- 1000-tour run : results/seeds/convergence/q97/n140_beta30_mt1000/

Field-name quirk (inherited from run_convergence_test.py): the
scalar `bkz_improvement_70_to_500` / `sdbkz_improvement_70_to_500`
are actually `70_to_final_tour_1000` deltas here. Canonical data =
`{bkz,sdbkz}_dln_per_tour` arrays with 1000 entries each.

Usage:
    nohup python3 scripts/run_convergence_n140_mt1000.py \
        > logs/convergence_n140_mt1000_stdout.log 2>&1 &
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import run_convergence_test

run_convergence_test.N = 140
run_convergence_test.BETA = 30
run_convergence_test.MAX_TOURS = 1000

run_convergence_test.main()
