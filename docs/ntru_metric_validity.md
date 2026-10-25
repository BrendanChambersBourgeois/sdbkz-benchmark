# NTRU metric validity: the d(LN) reference on NTRU bases

## Concern

The per-tour metric is `dln = mean_i |rankin_i − ref_i|` with `ref = ln_fixed_point(size, β)`, the Li–Nguyen fixed point for a random q-ary lattice under BKZ-β. An NTRU basis is not a random q-ary lattice: it carries a dense secret sublattice and a q-vector head, so its reduced profile follows the Z-shaped ZGSA model (Ducas–van Woerden, NTRU Fatigue 2021). Comparing it to the LWE fixed point can conflate structure with reduction dynamics.

## Is the divergence real?

Advantage re-derived from the stored profiles under three references, mean over 20 seeds per n (q=97, β=20):

| n | LN | GSA-zero | reference-free `mean\|r_bkz − r_sdbkz\|` |
|---|---|---|---|
| 67 | −0.010 | −0.010 | 0.030 |
| 73 | +9.68 | +28.1 | 32.7 |
| 79 | +1.65 | +1.65 | 1.65 |

The n=73 divergence survives every reference, including the reference-free one: BKZ and SD-BKZ end at different bases at the transition.

## Is the sign real?

No. In a q-sweep at n=89 (β=20, precision 500, 8 seeds per q) the signed advantage at q=257 is +1.56 under LN, −46 under ZGSA with slope 0.0192 and −78 with slope 0.028. NTRU has no canonical BKZ fixed point, so the signed SD-BKZ advantage is not a well-defined observable on NTRU. The unsigned divergence is:

| q / q_fatigue | 0.35 | 0.54 | 0.76 | 0.92 | 1.10 | 1.44 | 1.97 | 2.49 |
|---|---|---|---|---|---|---|---|---|
| divergence | 1.6 | 2.2 | 5.5 | 78.5 | 10.2 | 0.04 | 0.03 | 0.07 |

It rises toward fatigue, spikes at q=257 (7 of 8 seeds near 90, one near 0: one variant finds the dense sublattice, the other does not) and collapses above fatigue where both variants trivially crack the instance.

## The observable we report

Dense-sublattice discovery (DSD) per variant: the short-vector count snaps to exactly n and b1 reaches the overstretched floor.

| q | q/q_fat | BKZ short / b1 | SD-BKZ short / b1 |
|---|---|---|---|
| 211 | 0.76 | 96.6 / 0.16 | 96.5 / 0.28 |
| 257 | 0.92 | 93.1 / 0.51 | 89.0 / 1.97 |
| 307 | 1.10 | 89.0 / 1.97 | 89.0 / 1.97 |
| ≥401 | ≥1.44 | 89.0 / 1.97 | 89.0 / 1.97 |

At q=257 SD-BKZ finds the dense sublattice in 8 of 8 seeds, BKZ in 1 of 8. The DSD onset (50% crossing in q) is the NTRU result; the canonical criterion and trend come from `scripts/extract_dsd_onset.py --trend` (two-part test `#{gs < log√(2n·2/3)+0.5} ≤ n+1 ∧ min(gs) > 1.5`, up to 100 seeds per cell), which gives an SD-BKZ-before-BKZ onset gap that is near zero at n=67–79 and grows with n from n=89 (Paper 2, table tab:dsdgap). Where the exact secret is stored, `secret_exact_match` supersedes the flag.

Caveats: the DvW estimate q_fat ≈ 0.004·n^2.484 increasingly under-predicts the measured onset at finite n. A −345.388 floor in a stored profile is the double-precision measurement GSO returning a non-positive r_ii and substituting 1e-300; it is a measurement artefact, not an fplll defect and not a crack. `metric_float_type="mpfr"` avoids it.
