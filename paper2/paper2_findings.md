# Paper 2 — curated findings (NTRU SD-BKZ + g6k cross-engine)

Organized paper-2 view of the §NTRU-tagged entries in the canonical
append-log `paper_findings.md` (which stays the
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

Three regimes: tied (n≤67) → onset spike at ~27× the plateau standard
deviation (n=71–73, SD-BKZ cracks the dense sublattice on most instances) →
tight +1.5–1.7-nat plateau (n≥79, std 0.20–0.33). The onset spike EXCEEDS the plateau (non-monotonic). NTRU d(LN)
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

## 4. SD-BKZ DSD-onset GAP GROWS with dimension (5-point trend, seed-backed)
*(2026-06-11 canonical: n-DEPENDENT two-part criterion
`#{gs_lognorm < log√(2n·2/3)+0.5} <= n+1 AND min(gs)>1.5` (=2.888 at n=89),
50% rate crossing, fplll, up to 100 seeds/cell after the WSL2 ball-out
top-up; `extract_dsd_onset --trend`. Supersedes the 2026-06-08 frozen-2.888
extraction and the 2026-06-04 preliminary numbers.)*

| n | SD onset q | BKZ onset q | gap% |
|---|-----------|------------|------|
| 67 | 144.6 | 145.4 | 1 |
| 79 | 171.2 | 171.0 | 0 |
| 89 | 238.0 | 283.3 | 19 |
| 101 | 428.6 | 512.2 | 20 |
| 113 | 729.2 | 930.4 | 28 |

SD-BKZ reaches dense-sublattice-discovery at progressively lower q than BKZ
as n grows (≈1% at n≤79 — statistically zero — then 19/20/28%; NOT monotone
1→0). SENSITIVITY: freezing the threshold at its n=89 value 2.888 across n
(the 2026-06-08 extraction) shifts only the near-zero-gap rows (n=67 →
166.6/167.5, n=79 → 181.7/182.5, n=113 BKZ → 925.0, gap 27) — the gap trend
is threshold-robust. The n-dependent extraction also lands on the 2026-06-04
curated 146/149, 175/175 (provenance recovered: the "lost" values were the
n-dependent criterion all along; the discrepancy was the frozen 2.888). All 5 points seed-backed incl. the n=113 endpoint
(earlier "unreproducible" was an extractor glob bug, p250-only). n=127
EXCLUDED (fplll §8 cancellation + off-grid crack). DvW crack-vs-fatigue
formula under-predicts the circulant crack at finite n.
*(Historical: the 2026-06-04 preliminary table — 146/149, 175/175, 237/281,
426/514, 732/932 at ~15–20 seeds — is preserved in the canonical append-log.)*

## 5. §8 Kahan-patch validation #2 — n=127 contamination fixed (new modulus)
*(2026-06-04; `Dockerfile.fplll_patched`, `results/seeds/ntru_patched/`)*
fplll's §8 catastrophic-cancellation fix (Kahan GSO), first proven on q=3329
LWE (degeneracy 38%→0%), re-proven on NTRU q∈{971,1087,1201}: the 5
contaminated n=127 runs (4 BKZ + 1 SD-BKZ, q971 s4 → −0.113) recover b1
−345.388 → ~−0.1 (control band; patched controls stay in-band, per-seed
values move as expected). 208 transient clamps: 157 raw ∈ [−3.5,−0.1], 40
deeper (min −173). 5/12 patched SD-BKZ runs end at the −345.388 floor — NOT
residual contamination: genuine off-grid circulant cracks (resolved
2026-06-04), collapsed profiles bottom out at the clamp floor. Patch
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
- **Phase 4b RESOLVED (2026-06-06/08, supersedes the b1-only "gap reproduces"
  claim of 2026-06-05):** under the proper two-part DSD criterion the matched
  β=40 cross-engine picture is an **honest null** — q=137 = 0/100 on BOTH
  variants and BOTH engines; true DSD onset in (181,211] reached by SD and
  BKZ TOGETHER, no gap. Null is grid-resolution-limited (single 181→211 step
  ≈16% relative, bracketing cells N=20; q∈{191–199} fill running on WSL2 will
  sharpen it). The earlier "+10 at q137" was b1-only
  over-firing (criterion trap; audit record
  `results/validation/dsd_criterion_sensitivity.json`). Regime constraint:
  the DSD gap is a β=20 phenomenon, the sieve needs β≥40, the regimes do not
  overlap.
- **The real cross-engine result (CONFIRMED via artifact check, N=100,
  q=137):** the min-GS-clearing event (min(gs)>1.5 alone — aggressive tail
  reduction, explicitly NOT DSD) fires SD>BKZ on both engines (fplll 38/12,
  g6k 61/23) and under SD-BKZ the sieve leaves the shortest GS vector ≈4.9×
  longer (+1.59 nats; median log-norm 1.844 vs 0.255 — the earlier "~7×" was
  a log-norm ratio, scale-dependent; BKZ side 0.140 vs 0.104 shows no such
  gap). Artifact check PASSED: primal bit-identity 100/100, det conserved
  (median ~1e-6, max 1.3e-4), divergence asymmetric (g6k-only 24 vs
  fplll-only 1), 0 degenerate profiles.
  (`results/validation/sieve_vs_enum_min_gs_clearing.json`.)

## Open / next
- Onset-window fill q∈{191,193,197,199} (running on WSL2) → sharpen the
  ~196–211 onset band in the §5 null.
- n=89 β=40 densify to N=100 across all q + n=101 β=40 onset bracket
  (48h chain, running).
- n=127 crack is off-grid (uncracked to q≈1811); patched rerun is validation,
  not re-inclusion in the trend.
- Cite: Ducas-Espitau-Postlethwaite (β=40 + Z-shape geometry),
  Recursive-reduction (Rankin / rHF-blind framing), Rowell ch3, Deng-Jia 2023
  (sieving SD-BKZ precedent — speed vs detail framing).
