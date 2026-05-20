#!/usr/bin/env python3
"""
Convergence test at the crossover dimension: n=140, β=30.

The standard-tour data (70 tours) shows n=140 β=30 as the crossover point
(mean -0.035, 33% win rate). BUT BKZ converges by tour 70 while SD-BKZ
continues improving. At full convergence (500 tours), the crossover may
disappear — this run tests that hypothesis.

If SD-BKZ keeps improving at n=140 like it does at n=90, the apparent
crossover is an artifact of measuring at finite tour count, and the real
asymptotic story has SD-BKZ winning further into the dimension range
than the standard-tour benchmark suggests.

Usage:
    nohup python3 scripts/run_convergence_n140_beta30.py > logs/convergence_n140_stdout.log 2>&1 &
"""
import os
import sys

# Patch the convergence test constants before importing main
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import run_convergence_test

run_convergence_test.N = 140
run_convergence_test.BETA = 30
# Keep MAX_TOURS = 500 (same as the n=90 baseline)
# Keep NUM_WORKERS = 22

# Run
run_convergence_test.main()
