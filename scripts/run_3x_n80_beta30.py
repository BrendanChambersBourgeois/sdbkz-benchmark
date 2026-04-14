#!/usr/bin/env python3
"""Single-group 3x tour run: n=80, β=30. Queued after current run finishes."""
import runpy, sys, os

# Patch GROUPS before importing main
import run_3x_extended
run_3x_extended.GROUPS = [
    {"n": 80, "beta": 30, "normal_tours": 70, "triple_tours": 210},
]
run_3x_extended.main()
