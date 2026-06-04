"""Reduction-engine backends behind the `_bkz_core.run_single` seam.

Phase 2 of the g6k integration (the "engine seam"). The science driver
(`_bkz_core.run_single`) owns the tour loop, stagnation bookkeeping, and
metric extraction; it is engine-blind. WHICH reduction engine advances the
basis one tour at a time is the only thing that varies, and that variation
is isolated here.

Two backends:

  fplll  — the historical path. `BKZ.reduction(B, param, float_type="mpfr",
           precision=p)` once per tour over an `IntegerMatrix`. The byte
           sequence is IDENTICAL to the pre-seam inline loop (the param is
           rebuilt per tour exactly as before, the GSO is a fresh
           `GSO.Mat(B)` per call). This identity is the Phase 2 regression
           gate: scripts/verify.sh must stay green and the per-seed JSON
           must stay SHA-stable (timestamp aside).

  g6k    — the sieve path. One `pump_n_jump_bkz_tour` per tour over a
           `Siever`, under the Phase 0 determinism contract (threads=1,
           FPLLL.set_random_seed before the sieve; SieverParams has no
           'seed' key — no-op). Bit-identity is gated by the same primitive
           feeding scripts/g6k_probe.py: verify_g6k.sh must still hash
           cf22519d… / d4faf05a… (n=80,β=60,seed=42).

Each backend exposes the same tiny surface the driver needs:

    be = make_backend(name, B_init=..., beta=..., variant=..., seed=...,
                      precision=...)
    be.tour()              # advance the basis exactly one BKZ tour
    M = be.gso()           # an fpylll MatGSO, update_gso()'d, for metrics

`B_init` is the shared LLL-reduced starting basis (an `IntegerMatrix`); the
backend takes its OWN private copy so the driver can reuse `B_init` across
the bkz/sdbkz variants without aliasing.

OPEN (Phase 3 science — NOT decided here):
  * g6k has no settled SD-BKZ analog, so `variant="sdbkz"` on the g6k
    backend raises NotImplementedError rather than silently aliasing plain
    BKZ. The advantage metric (bkz_final_dln - sdbkz_final_dln) is therefore
    fplll-only until that semantics is fixed.
  * Multi-tour g6k determinism (re-seed-per-tour vs re-seed-once) is locked
    only for the single-tour probe today. The backend re-seeds ONCE at
    construction, matching the probe; >1 tour determinism is unproven and
    must be settled before any g6k production seed is generated.
"""
from __future__ import annotations

from typing import Any

from fpylll import BKZ, FPLLL, GSO, IntegerMatrix

FPLLL_BACKEND = "fplll"
G6K_BACKEND = "g6k"
BACKENDS = (FPLLL_BACKEND, G6K_BACKEND)


class _FplllBackend:
    """Per-variant fplll reducer. Byte-identical to the pre-seam inline loop.

    Constructs `BKZ.Param` inside `tour()` every call and a fresh
    `GSO.Mat(self.B)` inside `gso()` every call — deliberately mirroring the
    original `_bkz_core` body so the fplll call sequence (and thus the
    per-seed JSON bytes) does not move.
    """

    def __init__(self, *, B_init: IntegerMatrix, beta: int, variant: str,
                 precision: int) -> None:
        self.beta = beta
        self.precision = precision
        # Copy: the driver reuses B_init across variants; never alias it.
        self.B = IntegerMatrix(B_init)
        flags = BKZ.MAX_LOOPS | BKZ.AUTO_ABORT
        if variant == "sdbkz":
            flags |= BKZ.SD_VARIANT
        self._flags = flags

    def tour(self) -> None:
        param = BKZ.Param(self.beta, max_loops=1, flags=self._flags)
        BKZ.reduction(self.B, param, float_type="mpfr",
                      precision=self.precision)

    def gso(self) -> Any:
        M = GSO.Mat(self.B)
        M.update_gso()
        return M


class _G6kBackend:
    """Per-variant g6k reducer under the Phase 0 determinism contract.

    scripts/g6k_probe.py drives its sieve through this same backend, so the
    verify_g6k.sh exact-SHA gate covers this code path (a drift here trips
    the cf22519d… / d4faf05a… reference).
    """

    def __init__(self, *, B_init: IntegerMatrix, beta: int, variant: str,
                 seed: int) -> None:
        if variant == "sdbkz":
            raise NotImplementedError(
                "g6k has no settled SD-BKZ variant (Phase 3 science). "
                "Do not alias it to plain BKZ — the advantage metric would "
                "be meaningless. See docs/design_decisions.md ADR-006."
            )
        # Import lazily: the fplll path (and its container) has no g6k.
        from g6k import Siever, SieverParams
        from g6k.algorithms.bkz import pump_n_jump_bkz_tour

        self.beta = beta
        self._tour_fn = pump_n_jump_bkz_tour
        A = IntegerMatrix(B_init)  # g6k mutates the basis in place
        # Contract: re-seed FPLLL immediately before the sieve — the g6k
        # sampler draws from fplll's global RNG. threads=1 ONLY (MT sieve
        # is a nondeterministic insertion-order race). SieverParams has no
        # 'seed' key in this build (no-op) — do not add one.
        FPLLL.set_random_seed(seed)
        self.g6k = Siever(A, SieverParams(threads=1))

    def tour(self) -> None:
        from fpylll.tools.bkz_stats import dummy_tracer
        self._tour_fn(self.g6k, dummy_tracer, self.beta,
                      pump_params={"down_sieve": True})

    def reseed(self, seed: int) -> None:
        """Re-seed fplll's global RNG (the sieve sampler's source). Used to
        probe the multi-tour determinism policy (re-seed once at construction
        vs before every tour); see g6k_probe.py / ADR-007."""
        FPLLL.set_random_seed(seed)

    def gso(self) -> Any:
        self.g6k.M.update_gso()
        return self.g6k.M


def make_backend(name: str, *, B_init: IntegerMatrix, beta: int,
                 variant: str, seed: int, precision: int) -> Any:
    """Build the per-variant reducer for `name` ('fplll' | 'g6k').

    `variant` is "bkz" or "sdbkz"; `seed` and `precision` are taken by both
    signatures so the driver can call uniformly (each backend uses only what
    it needs). Raises ValueError on an unknown backend name.
    """
    if name == FPLLL_BACKEND:
        return _FplllBackend(B_init=B_init, beta=beta, variant=variant,
                             precision=precision)
    if name == G6K_BACKEND:
        return _G6kBackend(B_init=B_init, beta=beta, variant=variant,
                           seed=seed)
    raise ValueError(
        f"unknown backend {name!r}; expected one of {BACKENDS}"
    )
