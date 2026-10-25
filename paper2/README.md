# Paper 2 — NTRU SD-BKZ: dimension-onset advantage, fatigue, and the cross-engine DSD observable

In-repo home for the **second** paper (the first lives in `paper1/` —
SD-BKZ vs BKZ on LWE-Kannan, d(LN) vs RHF). Paper 2 extends the SD-BKZ
benchmark to **NTRU** and to a **second reduction engine (g6k)**.

**Status: draft manuscript, not yet deposited on a preprint server.** The
manuscript is `latex/sdbkz_paper2.tex` (build: `make -C paper2/latex`); its
figures are regenerated into `latex/figs/` by `make figs-paper2`. Paper 1 is
archived as published and is not revised: errors found in it later are
recorded in Paper 2's appendix "Corrections to the Companion Paper".

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
  numbers). Not kept current after 2026-09-27; the
  manuscript is the current record.
- `latex/` — the manuscript (`sdbkz_paper2.tex`, bib files, IACR class).
- `latex/figs/` — paper-2 figures, one module each under `analysis/plots/ntru_*`,
  driven by `analysis/paper2_figures.py`.

## Source data (in-repo)
- NTRU dimension/q sweeps (fplll): `results/seeds/ntru/`
- g6k cross-engine cells: `results/seeds/ntru_g6k/`
- n=127 patched-fplll rerun (inverted-sign patch build; see Appendix B):
  `results/seeds/ntru_patched/`
- n=127 rerun on `sdbkz-fplll-patched:kahan-v3` (premise withdrawn; see Appendix B):
  `results/seeds/ntru_patched_kahan_v3/`
- fplll mirrors of G6K frontier cells (outside the canonical manifest):
  `results/seeds/ntru_b2/`
- Cross-engine comparison records: `results/validation/`
- Metric validity: `docs/ntru_metric_validity.md`. ADRs 005–008 (g6k).
