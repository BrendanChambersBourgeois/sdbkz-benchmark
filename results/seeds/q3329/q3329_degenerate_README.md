# q=3329 degenerate-basis seeds (early dataset)

These 42 result files exhibit the catastrophic-cancellation failure mode in fplll's squared-form GSO update that is characterised in detail in **paper §8** ("Numerical Instability in fplll's GSO Update at Cryptographic Moduli"). At q=3329, the Cholesky-style recurrence

r(i,i) = ‖b_i‖² − Σ_{k<i} μ_{i,k}² · ‖b*_k‖²

is computed as a single scalar subtraction in `fplll/gso_interface.cpp:147–151` (function `MatGSOInterface<ZT,FT>::update_gso_row`) with no compensation, no reorthogonalisation, and no sign check. When this fires, at least one Gram–Schmidt vector crashes to the MPFR precision floor (`log‖b*_i‖ ≈ −345`), the per-tour d(LN) trajectory shows spikes of 100–300 nats, and the final d(LN) values are not interpretable as algorithm-quality measurements.

This directory is **kept as a historical reference dataset**; it is not the data the paper §8 characterisation is computed from.

## Canonical paper §8 dataset

The **100-seed, 1000-bit MPFR dataset** characterising the failure lives in the two directories:

- `results/q3329/n100_beta30_q3329_seed{11..100}.json` — 90 seeds (45 Intel 13900K + 45 AMD 9950X3D), disjoint from the cloud subset
- `results/cloud/n100_beta30_q3329_seed{1..10}.json` — 10 AWS Batch seeds

Together they form the 100-seed characterisation reported in paper §8.2 (38/100 = 38.0% degeneracy rate, Wilson 95% CI [29.1%, 47.8%], cross-machine reproducibility verified). Do **not** mix the 42 early seeds in this directory with the 100-seed paper dataset.

## What this directory contains

- **n=100, β=30, q=3329** — 20 seeds (originally 500-bit MPFR)
- **n=110, β=30, q=3329** — 22 seeds (originally 500-bit MPFR)

Each file uses the standard per-seed schema (`bkz_dln_per_tour`, `sdbkz_dln_per_tour`, `gs_lognorms_*`, etc.) but the trajectories include points where d(LN) spikes wildly because at least one Gram–Schmidt log-norm is numerically on the precision floor.

## Precision is not the fix (confirmed)

The files in this directory were originally labelled "corrupted 500-bit data". A re-run of the same seeds at 1000-bit MPFR produced bit-identical trajectories on the affected tours. Doubling the working precision does not close the gap because the root cause is arithmetic (uncompensated cancellation in the inner subtraction), not bit-width. The Kahan-compensated patch to `gso_interface.cpp:147–151` described in paper §8.3 reduces the hit rate from 38.0% (38/100 unpatched) to 0% (0/55 patched).

## Why these seeds are kept

1. **They document the failure mode before the root cause was known.** The dataset is useful as a "before" snapshot — every file demonstrates at least one tour where a GSO log-norm crosses the −100 boundary and the d(LN) trajectory spikes correspondingly.
2. **They are reproducible at any precision.** The behaviour is deterministic given the seed; paper §8.2 confirms the hit probability is a function of the lattice structure, not random FP noise.
3. **They are not used in any aggregate paper statistic.** Paper §8's 100-seed characterisation draws from the disjoint dataset described above.
4. **Project policy:** experimental data is never deleted, only quarantined. These remain here for researchers reproducing the §8.3 Kahan patch or studying the pre-patch failure mode.

## How to use these files

- **Do not include** in any aggregate statistics about SD-BKZ vs BKZ at q=3329 — use the 100-seed characterisation set instead.
- **Per-tour spike inspection:** every file has `bkz_dln_per_tour` and `sdbkz_dln_per_tour`. Spikes above 20 nats mark tours where the basis hit the degenerate region during that tour.
- **GSO inspection:** `gs_lognorms_bkz` and `gs_lognorms_sdbkz` show where the collapse occurred. Look for entries below −100.

## What is valid q=3329 data

- **`results/q3329/n50_beta30_q3329_seed*.json`** — 20 seeds, n=50 β=30, q=3329, 250-bit precision. Clean dataset at a dimension where the cancellation does not fire: mean SD-BKZ advantage **+0.437 nats**, 100% win rate. Reported in paper §3.2.
- **`results/q3329/n70_beta30_q3329_seed*.json`** and **`n80_beta30_q3329_seed*.json`** — 20 seeds each, also clean (0/20 degenerate at each dimension). Reported in paper §3.2 and §8.2.
- **`results/q3329/n90_beta30_q3329_seed*.json`** — 20 seeds, 1/20 degenerate at n=90 (the onset dimension, paper §8.2).
- **`results/q3329/n100_beta30_q3329_seed{11..100}.json` + `results/cloud/n100_beta30_q3329_seed{1..10}.json`** — 100 seeds, 1000-bit MPFR, the marquee §8.2 characterisation.

## Reproducing the spike check

```python
import json, glob

for f in sorted(glob.glob("n*_beta*_q3329_seed*.json")):
    d = json.load(open(f))
    all_tours = d["bkz_dln_per_tour"] + d["sdbkz_dln_per_tour"]
    max_spike = max(all_tours)
    gso_min = min(d["gs_lognorms_sdbkz"])
    print(f"{f}: max_spike={max_spike:.1f}, sd_gso_min={gso_min:.2f}, "
          f"advantage={d['advantage']:+.4f}")
```

Every file in this directory has at least one tour with d(LN) > 20 nats and at least one Gram–Schmidt log-norm below −100. The two are correlated: the spikes occur on tours where the GSO has just crashed into the precision floor via the uncompensated squared-form subtract in `gso_interface.cpp:147–151`.
