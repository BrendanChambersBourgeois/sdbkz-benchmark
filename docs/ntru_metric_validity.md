# NTRU metric validity — the d(LN) reference on NTRU bases (Phase 1)

**Status:** analysed 2026-06-03. Phase 1 (below) tested LN / GSA-zero /
reference-free and concluded the n≈71–73 divergence is real. The Phase 3
addendum (bottom) SHARPENS this with a ZGSA test: the BKZ-vs-SD-BKZ
*divergence* is real and reference-free, but the *signed* advantage flips
sign under ZGSA (artifact) — so report the unsigned divergence, NOT the
signed NTRU "advantage." Read the Phase 3 addendum for the settled verdict.

## The concern

The benchmark's per-tour metric is

    dln = mean_i | rankin_i − ref_i |,   advantage = bkz_dln − sdbkz_dln

where `rankin` is the Gram–Schmidt log-norm profile minus its own average
slope, and `ref = ln_fixed_point(size, β)` is the **Li–Nguyen BKZ
fixed point**. For NTRU the engine measures the *full* 2n basis (R* =
[0, 2n)) and compares against this same `ln_fixed_point`.

`ln_fixed_point` is, on inspection, a **GSA line** (per-step slope
`log_delta(β) = log(β/2πe)/(2β−2)`) — the fixed point for a *random
q-ary* lattice under BKZ-β. NTRU is **not** a random q-ary lattice: its
2n basis carries a dense secret sublattice and a q-vector head, so its
reduced profile follows the **ZGSA** (Z-shaped) model of Ducas–van Woerden
(NTRU Fatigue, 2021), not the LWE Li–Nguyen line. Comparing an NTRU
profile to the LWE fixed point can therefore conflate *structure* with
*reduction dynamics*.

## Literature

No closed-form Li–Nguyen-style Rankin fixed point exists for the NTRU
lattice. The field models the NTRU GS profile with:

- **GSA** — single linear slope (what `ln_fixed_point` already is).
- **ZGSA** — Z-shape: a flat q-vector head at `log q`, then a GSA slope.
  Specified for NTRU in Ducas–van Woerden 2021. The NTRU-appropriate
  reference.
- **CN11 simulator** — fpylll's BKZ simulator from the actual initial
  profile; the most accurate shape estimator, instance-specific.

(Sources: Ducas–van Woerden, *NTRU Fatigue* 2021; lattice-estimator
simulator docs — GSA / ZGSA / LGSA / CN11.)

## Empirical test — does the n=73 spike survive a reference change?

Re-derived the advantage **from the stored** `rankin_profile_{bkz,sdbkz}`
(no BKZ re-run) under three references, mean over 20 seeds/n:

| n  | LN (current) | GSA-zero (mean\|rankin\|) | reference-free divergence (mean\|r_bkz − r_sdbkz\|) |
|----|--------------|---------------------------|-----------------------------------------------------|
| 67 | -0.010       | -0.010                    | 0.030                                               |
| 73 | **+9.68**    | **+28.1**                 | **32.7**                                             |
| 79 | +1.65        | +1.65                     | 1.65                                                |

The n=73 divergence is large under **every** reference — including the
reference-free `mean|r_bkz − r_sdbkz|` (32.7 nats). BKZ and SD-BKZ
genuinely end at very different bases at the transition; the spike is
**not** an artifact of the Li–Nguyen reference. n=67 (~0) and n=79 (~tight
+1.6) are stable across references too.

A high-advantage n=73 seed (seed12): both ran ~50 tours, initial
d(LN)=52.8 → BKZ 34.5 / SD-BKZ 18.5, normal floors — SD-BKZ found a much
better-reduced basis (it cracks the dense sublattice; BKZ does not).

## Verdict / R\*

- The **qualitative** result (sharp SD-BKZ onset at n≈71–73, plateau for
  n≥79) is real and reference-robust → safe to keep building on.
- The **quantitative** advantage *scale* on NTRU is reported against the
  GSA-line (LN) reference, which is LWE-derived. NTRU magnitudes are on
  their own scale (NTRU full-basis d(LN) baseline ≈50 vs LWE ≈3) and are
  **not** directly comparable in nats to LWE advantages.
- **Fallback (now):** keep the GSA-line (`ln_fixed_point`) reference for
  NTRU, documented as an approximation. No metric-logic change → LWE bases
  stay byte-identical.
- **Future (accurate NTRU metric):** implement a ZGSA reference (DvW
  Z-shape) or use the CN11 simulator from each instance's initial profile,
  so NTRU advantage isolates dynamics from the q-ary structure. Defer until
  the metric seam (active-block-by-generator) lands and there is a third
  generator to justify the abstraction.

---

## Phase 3 addendum — q-sweep gated on ZGSA

Ran a fatigue q-sweep at fixed n=89 (fatigue q≈278), β=20, precision 500,
8 seeds/q, then re-derived the result under ZGSA (Z-shape, slope-swept) and
a reference-free divergence — BEFORE trusting any fatigue claim.

**Signed advantage is reference-artifact.** At q=257 (0.92× fatigue):
d(LN) advantage = +1.56, d(ZGSA, slope 0.0192) = −46, d(ZGSA, slope 0.028)
= −78. The sign and magnitude track the reference. Even the fixed-n
plateau (n≥79) sign-flips when the ZGSA slope nears the actual reduced-
profile slope (~0.027). Conclusion: NTRU has no canonical BKZ fixed point,
so the *signed* SD-BKZ advantage is not a well-defined observable on NTRU.

**The robust observable is the reference-free divergence**
`mean|rankin_bkz − rankin_sdbkz|` (unsigned). It needs no reference and
shows a clean fatigue signal:

| q/q_fatigue | 0.35 | 0.54 | 0.76 | 0.92 | 1.10 | 1.44 | 1.97 | 2.49 |
|-------------|------|------|------|------|------|------|------|------|
| divergence  | 1.6  | 2.2  | 5.5  | 78.5 | 10.2 | 0.04 | 0.03 | 0.07 |

Rises toward fatigue, **spikes ~78 at q=257** (bimodal: 7/8 seeds ~90, one
~0 — one variant cracks the dense sublattice, the other does not), then
**collapses to ~0 above fatigue** (both variants trivially crack the
overstretched instance, so they agree). A critical-transition signature at
q≈q_fatigue, reference-independent.

**Middle-third precursor thesis: NOT supported.** The mid-third divergence
stays flat (~0.2) through q=211 while the full basis is already elevated
(5.5); the signal leads in the q-vector head, the middle third lags. No
precursor in the middle third under any reference.

**Verdict:** the fatigue phenomenon is real and locatable reference-free,
but the SD-BKZ "advantage" magnitude/sign is not a valid NTRU observable.
Report the divergence, not the signed advantage. GSO health clean at
precision 500 for q≤691 (no new clamp events; the q=3329 floors were a
double-precision measurement artifact, not an fplll defect).

### DSD validation — is the q=257 peak real fatigue or the formula?

The "0.92× fatigue" framing leans on the DvW estimate q_fat≈0.004·n^2.484
(≈278 at n=89), unvalidated for this circulant. Direct check: does the
rank-n dense sublattice MEASURABLY appear at q=257? Signature = the
short-vector count snapping to exactly n (the dense sublattice is rank n)
with b1 hitting the overstretched floor.

Per-variant dense-sublattice-discovery (short = #{gs < log√(2n·2/3)+0.5}):

| q   | q/q_fat | BKZ short / b1 | SD-BKZ short / b1 |
|-----|---------|----------------|-------------------|
| 211 | 0.76    | 96.6 / 0.16    | 96.5 / 0.28       |
| 257 | 0.92    | 93.1 / 0.51    | **89.0 / 1.97**   |
| 307 | 1.10    | **89.0 / 1.97**| 89.0 / 1.97       |
| ≥401| ≥1.44   | 89.0 / 1.97    | 89.0 / 1.97       |

`short` snaps to exactly n=89 with b1→floor 1.97 — SD-BKZ at q=257, BKZ at
q=307. Per-seed at q=257: SD-BKZ finds the dense sublattice in **8/8**
seeds, BKZ in **1/8**. So the divergence peak IS real fatigue (the
sublattice appears there), not a formula artifact; DvW's 278 sits between
the two crack points (formula roughly right for the circulant).

**Clean observable (reference-free, physically grounded):** the DSD success
rate per variant vs q (short==n ∧ b1 at floor). SD-BKZ's DSD onset precedes
BKZ's (q=257 vs 307) — SD-BKZ cracks NTRU fatigue ~18% earlier in q. This,
not the signed d(LN) advantage, is the NTRU result to carry into Phase 4.

### Phase 4 — gap-vs-n trend (5 clean points, n=127 excluded)

> **SUPERSEDED.** Canonical trend = `scripts/extract_dsd_onset.py
> --trend` (two-part criterion `#{gs < log√(2n·2/3)+0.5} <= n+1 ∧ min(gs) >
> 1.5`, n-dependent threshold, 50%-rate crossing, up to 100 seeds/cell after
> the 2026-06-07 ball-out): 67: 144.6/145.4 g1 · 79: 171.2/171.0 g0 ·
> 89: 238.0/283.3 g19 · 101: 428.6/512.2 g20 · 113: 729.2/930.4 g28 (paper-2
> Table tab:dsdgap). The table below is the original ~15–20-seed extraction
> under this doc's `short==n ∧ b1→floor` criterion — kept as history; it
> lands within grid resolution of the canonical numbers.

DSD onset (rate crossing 50%; short-count→n ∧ b1→floor) per variant, swept
in q across each n's crack zone, ~15–20 seeds/cell:

| n   | dim | SD onset (q) | BKZ onset (q) | SD/q_fat | BKZ/q_fat | gap% |
|-----|-----|--------------|---------------|----------|-----------|------|
| 67  | 134 | 146          | 149           | 1.07     | 1.08      | 2    |
| 79  | 158 | 175          | 175           | 0.85     | 0.85      | 0    |
| 89  | 178 | 237          | 281           | 0.85     | 1.01      | 18   |
| 101 | 202 | 426          | 514           | 1.12     | 1.35      | 21   |
| 113 | 226 | 732          | 932           | 1.46     | 1.85      | 27   |

**The SD-BKZ DSD-onset gap GROWS with dimension** — ~0 at small n, then
18 → 21 → 27% for n = 89, 101, 113. SD-BKZ reaches dense-sublattice
discovery at a progressively lower q (relative to BKZ) as n grows. The
crack-vs-fatigue ratio also drifts up steeply (BKZ crack 1.0× → 1.85×
q_fatigue), so the DvW estimate q_fat≈0.004·n^2.484 increasingly
under-predicts the measured crack for the circulant at finite n.

**n=127 EXCLUDED — no exact-recovery field, thin cells.** None of the 152
n=127 seeds records `secret_exact_match_*`, and the cells above q=971 hold
3-4 seeds. The DSD flag stays ≤25% up to q=1811, but that is the flag, not
the lattice: b1 has the key's norm on SD 4/4 and BKZ 3/4 legs at q=1811
(SD from q=1201). Excluded from the trend; the 5 clean points already
establish the dimension-dependence. Separately, 16/152 n=127 seeds carry a
−345.388 floor on 17 legs: the double-precision GSO that measured these
profiles (`GSO.Mat` default) returned a non-positive `r_ii` at one tail
position, substituted with CLAMP_FLOOR_R (1e-300), giving 0.5·ln(1e-300). It
is a measurement artifact, not an fplll reduction defect and not a crack: b1
stays near the q-vector and the leg's d(LN) is meaningless (>100 nats). At
n=67–113 (β=20) one leg floors (n=113 q=773 seed 13 BKZ; its DSD verdict is
unchanged when re-measured in MPFR). (NB: these 16 seeds predate clamp
logging, wired into the NTRU worker on 2026-06-04; later clamps go to
results/clamp_events.jsonl (kept locally; available on request) without
n/q/seed, so the min-gs ≤ −100 filter is how a floor is matched to a seed.
`metric_float_type="mpfr"` avoids them.)
