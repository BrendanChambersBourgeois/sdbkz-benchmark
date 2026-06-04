# Morning report — g6k cross-engine (night 2026-06-04 → 05)

Short-vector "fired" = final `gs_lognorms_sdbkz[0] < 3.5` (below the q-vector
floor ln(97)≈4.57). NTRU, q=97, β=40, mt=50, 20 seeds/cell.

| n | g6k fired | fplll fired | both | Jaccard |
|---|-----------|-------------|------|---------|
| 67  | (pilot, RHF-blind clean) | — | — | — |
| 89  | 2/20 (s17,19) | 1/20 (s19) | s19 | 0.50 |
| 101 | 0/20 | 0/20 | — | 1.00 |
| 113 | 0/20 | 0/20 | — | 1.00 |

## Verdict (INC-41 resolved)
- **g6k self-dual construction is SOUND.** n=101/113: the two engines agree
  perfectly (0/0). No spurious g6k firing → not high-tour drift. seed-19 at
  n=89 fires in BOTH engines at the identical gs[0]=2.332. With H2
  (orientation verified primal), the construction is validated.
- **n=89 firing is real but SPARSE, not a growing DSD-onset trend.** It
  appears at n=89, vanishes at n=101/113. At fixed q=97, larger n is harder
  (further below fatigue q_fat≈0.004·n^2.484) → short vectors rarer with n.
- **"RHF blind" is regime-dependent**: clean where no short vector is found
  (n=101/113); breaks at the rare n=89 short-vector seeds (RHF sees them).
- **Next experiment to map DSD-onset**: sweep q TOWARD fatigue at fixed n
  (deferred Phase-4(b)), not fixed-q across n.

Per-seed + Jaccard: `results/validation/g6k_sd_xengine_n{89,101,113}_mt50.json`.

## Ops note
The fplll cross-engine seeds + these records were written by `sdbkz-benchmark:ci`
running as ROOT (stale image vs its Dockerfile's USER line) — root-owned
files, chowned back. See INC-40 (wider recurrence). Fix: rebuild :ci or add
`--user $(id -u):$(id -g)` to bind-mounted docker runs.
