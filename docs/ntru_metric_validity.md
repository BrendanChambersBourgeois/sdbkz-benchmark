# NTRU metric validity — the d(LN) reference on NTRU bases (Phase 1)

**Status:** analysed 2026-06-03. The NTRU SD-BKZ advantage signal (sharp
onset at n≈71–73, stable +1.5 plateau for n≥79) is **real and
reference-robust**, but the *magnitude scale* uses an LWE-derived
reference; a physically-correct NTRU reference (ZGSA / CN11) is future work.

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
