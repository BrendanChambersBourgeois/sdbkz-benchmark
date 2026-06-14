# Paper 2 — NTRU SD-BKZ: dimension-onset advantage, fatigue, and the cross-engine DSD observable

In-repo home for the **second** paper (the first lives in `paper/` —
SD-BKZ vs BKZ on LWE-Kannan, d(LN) vs RHF). Paper 2 extends the SD-BKZ
benchmark to **NTRU** and to a **second reduction engine (g6k)**.

**Status: IN PROGRESS — no manuscript yet.** This dir collects findings +
figures as the science settles; the LaTeX/HTML manuscript (and the
symmetric `paper/`→`paper1/` rename) come later, once the cross-engine
DSD-onset results are in. See `paper2_findings.md` for the curated results.

## Thesis (paper 2)
The SD-BKZ advantage is **not LWE-specific**. On NTRU it shows a sharp
**dimension-onset** (around n≈71–73 at q=97) and a **fatigue** signal as q
crosses the overstretched point — best captured by the **reference-free
BKZ-vs-SD-BKZ profile divergence / DSD observable**, NOT signed d(LN) (NTRU
has no canonical fixed point — signed advantage is a reference artifact).
The g6k extension asks whether the same DSD-onset reproduces on a **sieve**
oracle, and confirms (paper 1's other half) that **RHF is blind** to the
SD-BKZ difference while d(LN)/DSD sees it — now cross-engine.

## Layout
- `paper2_findings.md` — curated paper-2 results (synthesis + the key
  numbers). The canonical chronological append-log remains
  `paper_findings.md` (the §NTRU-tagged entries); this is
  the organized paper-2 view of it.
- `figs/` — paper-2 figures (none yet; placeholder).

## Source data (in-repo)
- NTRU dimension/q sweeps (fplll): `results/seeds/ntru/`
- g6k cross-engine cells: `results/seeds/ntru_g6k/`
- §8 Kahan-patch validation #2: `results/seeds/ntru_patched/`
- Cross-engine comparison records: `results/validation/`
- Metric validity: `docs/ntru_metric_validity.md`. ADRs 005–008 (g6k).
