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

RESOLVED (Phase 3 science):
  * g6k SD-BKZ = self-dual pump-BKZ (a primal pump-n-jump tour followed by a
    dual pass), validated against fplll `BKZ.SD_VARIANT` — see ADR-008. The
    advantage metric (bkz_final_dln - sdbkz_final_dln) is now defined on both
    engines; the g6k backend implements both variants (see _G6kBackend.tour).
  * Multi-tour g6k determinism is settled (ADR-007, Gate 1): the backend
    re-seeds ONCE at construction and every sub-tour runs threads=1, so >1 tour
    reduction is deterministic. g6k production seeds are generated on this
    contract.
"""
from __future__ import annotations

import time
from typing import Any

from fpylll import BKZ, FPLLL, GSO, IntegerMatrix
from fpylll.tools.bkz_stats import Tracer

FPLLL_BACKEND = "fplll"
G6K_BACKEND = "g6k"
BACKENDS = (FPLLL_BACKEND, G6K_BACKEND)


class _SieveTimer(Tracer):
    """Opt-in per-pass sieve accounting for the g6k backend.

    Every context other than a pump is a sieve call, counted under its label
    (gauss, hk3, bgj1, ... and anything a build adds). Reads only clocks,
    ``g6k.n`` (sieve dimension) and ``len(g6k)`` (db size) when a context
    exits. g6k's own SieveTreeTracer also calls
    ``M.update_gso()`` on every exit, which this deliberately does not, so the
    reduction is the dummy_tracer one (tests/test_sieve_trace_g6k.py).
    """

    def __init__(self, g6k: Any) -> None:
        Tracer.__init__(self, g6k)
        self._open: list[tuple[Any, float, float]] = []
        self.reset()

    def reset(self) -> None:
        self.by_alg: dict[str, list] = {}  # alg -> [calls, cpu_s, wall_s]
        self.by_dim: dict[int, list] = {}  # sieve dim -> [calls, cpu_s]
        self.max_db = 0
        self.pumps: list[tuple[int, float, float]] = []  # (index, cpu, wall)

    def enter(self, label: Any, **kwds: Any) -> None:
        self._open.append((label, time.process_time(), time.monotonic()))

    def exit(self, **kwds: Any) -> None:
        label, c0, w0 = self._open.pop()
        cpu, wall = time.process_time() - c0, time.monotonic() - w0
        kind = str(label[0] if isinstance(label, tuple) else label)
        if kind == "pump":
            self.pumps.append((len(self.pumps), cpu, wall))
        else:
            a = self.by_alg.setdefault(kind, [0, 0.0, 0.0])
            a[0] += 1
            a[1] += cpu
            a[2] += wall
            d = self.by_dim.setdefault(int(self.instance.n), [0, 0.0])
            d[0] += 1
            d[1] += cpu
            self.max_db = max(self.max_db, len(self.instance))

    def summary(self, top: int = 5) -> dict[str, Any]:
        """One pass (pump-n-jump tour), compact enough for a jsonl record."""
        slow = sorted(self.pumps, key=lambda p: p[1], reverse=True)[:top]
        return {
            "pumps": len(self.pumps),
            "by_alg": {k: [c, round(cpu, 3), round(w, 3)]
                       for k, (c, cpu, w) in sorted(self.by_alg.items())},
            "by_dim": {str(k): [c, round(cpu, 3)]
                       for k, (c, cpu) in sorted(self.by_dim.items())},
            "max_db": self.max_db,
            "slowest_pumps": [[i, round(c, 3), round(w, 3)]
                              for i, c, w in slow],
        }


class _FplllBackend:
    """Per-variant fplll reducer. Byte-identical to the pre-seam inline loop.

    Constructs `BKZ.Param` inside `tour()` every call and a fresh
    `GSO.Mat(self.B)` inside `gso()` every call — deliberately mirroring the
    original `_bkz_core` body so the fplll call sequence (and thus the
    per-seed JSON bytes) does not move.
    """

    def __init__(self, *, B_init: IntegerMatrix, beta: int, variant: str,
                 precision: int, metric_float_type: str = "double") -> None:
        self.beta = beta
        self.precision = precision
        self.metric_float_type = metric_float_type
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
        # metric_float_type gates ONLY this measurement GSO (the reduction in
        # tour() is already mpfr). Default "double" keeps the historical call
        # byte-identical; "mpfr" (at the ambient FPLLL precision the driver
        # set) removes the catastrophic get_r cancellation at frontier dims
        # (dim 334 double GSO yields r<=0, the -345 clamp sentinel; mpfr none).
        if self.metric_float_type == "double":
            M = GSO.Mat(self.B)
        else:
            M = GSO.Mat(self.B, float_type=self.metric_float_type)
        M.update_gso()
        return M


class _G6kBackend:
    """Per-variant g6k reducer under the Phase 0 determinism contract.

    scripts/g6k_probe.py drives its sieve through this same backend, so the
    verify_g6k.sh exact-SHA gate covers this code path (a drift here trips
    the cf22519d… / d4faf05a… reference).
    """

    def __init__(self, *, B_init: IntegerMatrix, beta: int, variant: str,
                 seed: int, sieve_trace: bool = False) -> None:
        if variant not in ("bkz", "sdbkz"):
            raise ValueError(f"unknown g6k variant {variant!r}")
        # Import lazily: the fplll path (and its container) has no g6k.
        from g6k import Siever, SieverParams
        from g6k.algorithms.bkz import pump_n_jump_bkz_tour

        self.beta = beta
        self.variant = variant
        self._tour_fn = pump_n_jump_bkz_tour
        A = IntegerMatrix(B_init)  # g6k mutates the basis in place
        # Contract: re-seed FPLLL immediately before the sieve — the g6k
        # sampler draws from fplll's global RNG. threads=1 ONLY (MT sieve
        # is a nondeterministic insertion-order race). SieverParams has no
        # 'seed' key in this build (no-op) — do not add one.
        FPLLL.set_random_seed(seed)
        self.g6k = Siever(A, SieverParams(threads=1))
        # sieve_trace: per-pass summaries of the last tour, read by the
        # driver's tour_cb; None when tracing is off.
        self._timer = _SieveTimer(self.g6k) if sieve_trace else None
        self.tour_stats: dict[str, Any] | None = None

    def _pnj(self) -> dict[str, Any] | None:
        if self._timer is None:
            from fpylll.tools.bkz_stats import dummy_tracer
            self._tour_fn(self.g6k, dummy_tracer, self.beta,
                          pump_params={"down_sieve": True})
            return None
        self._timer.reset()
        self._tour_fn(self.g6k, self._timer, self.beta,
                      pump_params={"down_sieve": True})
        return self._timer.summary()

    def tour(self) -> None:
        """One tour. "bkz" = one primal pump-n-jump BKZ tour. "sdbkz" =
        self-dual: a primal pump-n-jump tour followed by a DUAL one, run under
        ``temp_params(dual_mode=…)`` flipped — g6k's documented dual mode runs
        all operations on the dual basis with bounds reflected about full_n/2
        (the same mechanism g6k's own ``slide_tour`` uses for its dual pass).
        This mirrors fplll ``BKZ.SD_VARIANT`` (primal+dual per loop) and is
        validated end-to-end against it on matched lattices (ADR-008). Both
        sub-tours are threads=1, so the self-dual tour is deterministic
        (ADR-007)."""
        stats = {"primal": self._pnj()}
        if self.variant == "sdbkz":
            with self.g6k.temp_params(
                dual_mode=not self.g6k.params.dual_mode
            ):
                stats["dual"] = self._pnj()
        if self._timer is not None:
            self.tour_stats = stats

    def reseed(self, seed: int) -> None:
        """Re-seed fplll's global RNG (the sieve sampler's source). Used to
        probe the multi-tour determinism policy (re-seed once at construction
        vs before every tour); see g6k_probe.py / ADR-007."""
        FPLLL.set_random_seed(seed)

    def gso(self) -> Any:
        self.g6k.M.update_gso()
        return self.g6k.M


def make_backend(name: str, *, B_init: IntegerMatrix, beta: int,
                 variant: str, seed: int, precision: int,
                 metric_float_type: str = "double",
                 sieve_trace: bool = False) -> Any:
    """Build the per-variant reducer for `name` ('fplll' | 'g6k').

    `variant` is "bkz" or "sdbkz"; `seed` and `precision` are taken by both
    signatures so the driver can call uniformly (each backend uses only what
    it needs). `metric_float_type` gates the fplll backend's MEASUREMENT
    GSO only ("double" = historical, "mpfr" = cancellation-free at high
    dim); the g6k backend measures through the Siever's own GSO and rejects
    any non-default value. Raises ValueError on an unknown backend name.
    """
    if name == FPLLL_BACKEND:
        if sieve_trace:
            raise ValueError("sieve_trace is g6k-only")
        return _FplllBackend(B_init=B_init, beta=beta, variant=variant,
                             precision=precision,
                             metric_float_type=metric_float_type)
    if name == G6K_BACKEND:
        if metric_float_type != "double":
            raise ValueError(
                "metric_float_type is fplll-only; the g6k backend measures "
                f"through the Siever's GSO (got {metric_float_type!r})"
            )
        return _G6kBackend(B_init=B_init, beta=beta, variant=variant,
                           seed=seed, sieve_trace=sieve_trace)
    raise ValueError(
        f"unknown backend {name!r}; expected one of {BACKENDS}"
    )
