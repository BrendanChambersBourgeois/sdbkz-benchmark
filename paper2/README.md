# Paper 2 — NTRU SD-BKZ: dimension onset, fatigue and the cross-engine DSD observable

Draft manuscript: `latex/sdbkz_paper2.tex` (`make -C paper2/latex`); figures regenerate into `latex/figs/` via `make figs-paper2` from `analysis/paper2_figures.py` and `analysis/plots/ntru_*`. Paper 1 is archived as published; its later corrections are recorded in Paper 2's appendix "Corrections to the Companion Paper".

Thesis: the SD-BKZ advantage is not LWE-specific. On NTRU it shows a sharp dimension onset and a fatigue signal as q crosses the overstretched point, captured by the reference-free dense-sublattice-discovery (DSD) observable rather than signed d(LN) (NTRU has no canonical fixed point; see `docs/ntru_metric_validity.md`). The G6K extension checks the same onset on a sieve oracle.

Source data: `results/seeds/ntru/` (fplll), `results/seeds/ntru_g6k/` and `ntru_g6k_reject/` (G6K), `ntru_exact` / `ntru_g6k_exact` (exact secret match), `ntru_patched_kahan_v3/` (Appendix B), `ntru_b2/` (fplll mirrors of G6K frontier cells, outside the manifest), `results/validation/` (cross-engine records). Claims ledger: `results/paper_claims/paper2_claims.json`.
