"""Lattice basis generators for the SD-BKZ benchmark.

Each generator is a pure, seeded function that returns a basis the engine
can reduce. The engine takes ``(basis, strategy)`` and is agnostic to the
source; ``run_campaign`` dispatches generators by name (see the generators
refactor backlog, 2026-06-03).

Generators:
  - ``build_lwe_kannan`` — LWE-Kannan embedding (q-ary + A-embedding +
    identity + error row), the existing benchmark construction.
"""
from generators.lwe_kannan import build_lwe_kannan

__all__ = ["build_lwe_kannan"]
