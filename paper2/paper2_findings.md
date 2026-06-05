# Paper 2 — curated findings (NTRU SD-BKZ + g6k cross-engine)

Organized paper-2 view of the §NTRU-tagged entries in the canonical
append-log `/mnt/hgfs/Research/paper_findings.md` (which stays the
append-only chronological source). Numbers below trace to that log + the
in-repo seed data. Update this file when a paper-2 result lands.

---

## 1. NTRU SD-BKZ advantage has a sharp DIMENSION-ONSET (then a plateau)
*(paper_findings 2026-06-03; campaign `ntru`, q=97, β=20, 50 tours, 20 seeds/n, full-basis [0,2n) metric)*

| n | mean adv | std | seeds>0 | regime |
|---|----------|-----|---------|--------|
| 59–67 | ~0 (−0.01) | tight | 3–9/20 | BKZ ≈ SD-BKZ |
| 71 | **+4.35** | 5.59 | 16/20 | onset (bimodal −6.7…+13.4) |
| 73 | **+9.68** | 5.21 | 19/20 | onset (range −5.1…+16.0) |
| 79–89 | +1.5 | ~0.2 | 20/20 | stable plateau |

Three regimes: tied (n≤67) → onset spike with ~25× variance (n=71–73, SD-BKZ
cracks the dense sublattice on most instances) → tight +1.5-nat plateau
(n≥79). The onset spike EXCEEDS the plateau (non-monotonic). NTRU d(LN)
baseline (~50) is ~15× the LWE-Kannan scale, so magnitudes are on their own
scale (sign + structure comparable, not raw nats).

## 2. The n=71–73 spike is REFERENCE-ROBUST (metric-validity)
*(2026-06-03; `docs/ntru_metric_validity.md`)*
d(LN) uses the Li–Nguyen GSA fixed point (random-q-ary, LWE-derived); NTRU is
not random q-ary (q-vector head + dense sublattice → ZGSA Z-shape). The spike
survives re-derivation under 3 references → real, not a reference artifact.
BUT: **signed d(LN) on NTRU is a reference artifact in general** — report the
**reference-free** BKZ-vs-SD-BKZ profile divergence / DSD observable, not
signed advantage.

## 3. NTRU FATIGUE signal is real, reference-free (q-sweep)
*(2026-06-03, Phase 3)* The reference-free BKZ-vs-SD-BKZ profile divergence
**peaks at q ≈ q_fatigue** (n=89: peak near q≈257). This is the defensible
NTRU fatigue observable.

## 4. SD-BKZ DSD-onset GAP GROWS with dimension (5-point trend)
*(2026-06-04, Phase 4; reference-free DSD onset, ~15–20 seeds/cell)*

| n | SD onset q | BKZ onset q | gap% |
|---|-----------|------------|------|
| 67 | 146 | 149 | 2 |
| 79 | 175 | 175 | 0 |
| 89 | 237 | 281 | 18 |
| 101 | 426 | 514 | 21 |
| 113 | 732 | 932 | 27 |

SD-BKZ reaches dense-sublattice-discovery at progressively lower q than BKZ
as n grows (gap 0 → 27%). n=127 EXCLUDED (fplll §8 cancellation + off-grid
crack). DvW crack-vs-fatigue formula under-predicts the circulant crack at
finite n.

## 5. §8 Kahan-patch validation #2 — n=127 contamination fixed (new modulus)
*(2026-06-04; `Dockerfile.fplll_patched`, `results/seeds/ntru_patched/`)*
fplll's §8 catastrophic-cancellation fix (Kahan GSO), first proven on q=3329
LWE (degeneracy 38%→0%), re-proven on NTRU q∈{971,1087,1201}: the 4
contaminated n=127 seeds recover b1 −345.388 → ~−0.1 (control band). Patch
validated on 2 modulus families; `make check` 15/15.

## 6. g6k cross-engine extension (Phase 4) — IN PROGRESS
*(2026-06-04/05; ADRs 005–008, `results/seeds/ntru_g6k/`, `results/validation/`)*
- g6k wired as a second reduction engine (engine seam, self-dual pump-BKZ
  validated vs fplll SD_VARIANT). Both determinism + SD-semantics gates clear.
- **Paper-1 thesis reproduced cross-engine**: RHF blind to the SD-BKZ
  difference, d(LN)/DSD sees it — but **regime-dependent** (breaks only when
  SD finds a short vector). Lines up with Rowell (RHF-equal under a non-exact
  oracle; we measure past it).
- **g6k self-dual construction validated sound** (INC-41 resolved): at
  n=101/113 g6k and fplll agree perfectly; the n=89 short-vector events are
  real-but-sparse, corroborated by fplll (seed 19 exact gs[0]=2.332 match).
- **Phase 4b (q-sweep, n=89, β=40)**: the **DSD-onset gap REPRODUCES on the
  sieve engine** (reference-free, b1>1.5):

  | q | SD DSD | BKZ DSD | gap |
  |---|--------|---------|-----|
  | 97,113 | 0/20 | 0/20 | 0 (pre-onset) |
  | **137** | **14/20** | **4/20** | **+10** (SD-only 11) |
  | 157 | 20/20 | 19/20 | +1 |
  | 181,211,…,521 | 20/20 | 20/20 | 0 (saturated) |

  At q=137 SD-BKZ cracks DSD where BKZ does not — **SD onset ≈137 < BKZ
  onset ≈157**. Lower q than the β=20 fplll onset (SD 237), as expected
  (stronger reduction → lower onset). Visible ONLY reference-free: signed
  d(LN) goes −30.8 at q=137 (DSD Z-profile far from the LWE reference —
  reference-artifact, demonstrated cross-engine).
  (`results/validation/g6k_dsd_onset_n89_beta40.json`.)
  - **Correction:** the first window (q=211–521) was all post-saturation; the
    "gap is β=20-only / regime-constrained" claim from it was premature
    (superseded — same over-claim-from-a-narrow-window error as INC-41).
  - Next: confirm the SD<BKZ ordering with more seeds + a finer q-grid around
    120–160; matched fplll β=40 q-sweep for the engine-to-engine onset.

## Open / next
- Phase 4b verdict (g6k DSD-onset curve) + matched fplll β=40 q-sweep.
- Tighten the 5-point DSD-onset trend (more seeds/cell, confirm the slope).
- n=127 crack is off-grid (uncracked to q≈1811); patched rerun is validation,
  not re-inclusion in the trend.
- Cite: Ducas-Espitau-Postlethwaite (β=40 + Z-shape geometry),
  Recursive-reduction (Rankin / rHF-blind framing), Rowell ch3.
