"""Lattice basis generators for the SD-BKZ benchmark.

Each generator is a pure, seeded function that returns a basis the engine
can reduce. The engine takes ``(basis, strategy)`` and is agnostic to the
source; ``run_campaign`` dispatches generators by name (see the generators
refactor backlog, 2026-06-03).

Generators:
  - ``build_lwe_kannan`` — LWE-Kannan embedding (q-ary + A-embedding +
    identity + error row), the existing benchmark construction.
"""
from generators.lwe_kannan import build_lwe_kannan, kannan_m
from generators.ntru import build_ntru


def _lwe_kannan(n: int, q: int, seed: int) -> list[list[int]]:
    """Registry adapter: the uniform ``(n, q, seed) -> L`` calling
    convention every generator exposes. The Kannan m=2n contract is
    carried inside here (via kannan_m) so callers — and the engine —
    stay source-agnostic; only the basis L crosses the boundary."""
    L, _, _ = build_lwe_kannan(n, kannan_m(n), q, seed=seed)
    return L


def _ntru(n: int, q: int, seed: int) -> list[list[int]]:
    """Registry adapter for NTRU: ring degree N=n, lattice dim 2N, no m."""
    L, _, _ = build_ntru(n, q, seed=seed)
    return L


# name -> uniform generator callable. New generators register here; the
# engine and run_campaign dispatch by these names alone.
GENERATORS = {
    "lwe_kannan": _lwe_kannan,
    "ntru": _ntru,
}


def _ntru_block_start(n: int) -> int:
    raise NotImplementedError(
        "NTRU metric active-block start is undecided (the 'R*' research "
        "decision): which block of the 2N basis defines reduction success "
        "for fatigue is not the LWE-Kannan projected-sublattice convention. "
        "Decide R* before routing NTRU through the BKZ engine; ntru_smoke "
        "only builds + structurally verifies bases."
    )


# name -> active-block start m for metrics_from_gso's [m, dim) window. The
# generator owns this convention; the engine is metric-blind and just uses
# the number. LWE-Kannan: m=2n (the projected sublattice with the embedded
# target). NTRU: gated on the R* decision (see _ntru_block_start).
METRIC_BLOCK_START = {
    "lwe_kannan": kannan_m,
    "ntru": _ntru_block_start,
}


def get_metric_block_start(name: str):
    """Resolve a generator name to its ``m(n) -> active-block start``
    callable for metrics_from_gso. Raises ValueError on unknown name."""
    try:
        return METRIC_BLOCK_START[name]
    except KeyError:
        raise ValueError(
            f"unknown generator {name!r}; available: {sorted(METRIC_BLOCK_START)}"
        ) from None


def available_generators() -> frozenset[str]:
    """Set of registered generator names (for config validation)."""
    return frozenset(GENERATORS)


def get_generator(name: str):
    """Resolve a generator name to its uniform ``(n, q, seed) -> L``
    callable. Raises ``ValueError`` (which the config layer surfaces as
    a ConfigError) on an unknown name."""
    try:
        return GENERATORS[name]
    except KeyError:
        raise ValueError(
            f"unknown generator {name!r}; available: {sorted(GENERATORS)}"
        ) from None


__all__ = [
    "build_lwe_kannan", "kannan_m", "build_ntru",
    "GENERATORS", "available_generators", "get_generator",
    "METRIC_BLOCK_START", "get_metric_block_start",
]
