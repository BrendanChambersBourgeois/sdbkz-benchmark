# fplll Gram–Schmidt cancellation — numerical findings + mitigation

**Status**: numerical-correctness finding at cryptographic moduli; Kahan-compensated patch ships at [`patches/fplll_gso_kahan.patch`](../../patches/fplll_gso_kahan.patch). Upstream issue filing queued pre-publication; filing date + issue number will be recorded in the timeline section below once filed.

**Paper reference**: §8 of [`paper/sdbkz_paper.pdf`](../../paper/sdbkz_paper.pdf) (LaTeX source: [`paper/latex/sdbkz_paper_latex.tex`](../../paper/latex/sdbkz_paper_latex.tex)).

**Classification**: this is a new instance of a known failure family (fpylll #272 — FP exception on linearly dependent matrices, fplll #237 — numerical stability tests). Not a new bug class. The novelty is (a) a concrete reproducer at canonical ML-KEM parameters, (b) a verified 30-line mitigation, and (c) cross-vendor FP execution reproduction.

---

## Summary

`fplll::MatGSOInterface<ZT,FT>::update_gso_row` at `fplll/gso_interface.cpp:147–151` computes the diagonal squared Gram–Schmidt norm via the Cholesky-style recurrence

```
r(i,i) = ‖b_i‖² − Σ_{k<i} μ(i,k)² · ‖b*_k‖²
```

as a naive in-place subtraction loop. No compensated summation. No sign check on the output. No reorthogonalization trigger. Every BKZ tour, every LLL call, every `get_r()` query — for every `FT` instantiation including `mpfr_t` — funnels through this one loop.

At cryptographic moduli (specifically tested: q=3329 for ML-KEM, with n ≥ 100), the `‖b_i‖²` and `Σ μ² · ‖b*_k‖²` operands approach each other in magnitude during reduction. Catastrophic cancellation follows. The residual loses all significance, occasionally flipping sign. The diagonal `r(i,i)` — a squared norm, mathematically non-negative — becomes a finite negative number. Downstream `get_r()` callers either propagate it as a wrong-but-finite contribution, or clamp it defensively and lose signal.

---

## Reproducer

```bash
# Clone repo at the tag that includes the q=3329 headline dataset
git clone https://github.com/BrendanChambersBourgeois/sdbkz-benchmark
cd sdbkz-benchmark
git checkout v1.3.1

# Build the pinned image (fpylll 0.6.4 bundles fplll 5.5.0,
# libfplll.so.9.0.0)
docker build -t sdbkz-benchmark:ci .

# Run one smoke seed at the canonical parameters. Expected behavior:
# at least one tour prints a "WARNING: 1 get_r values <= 0" line and
# logs the raw negative value to results/clamp_events.jsonl.
docker run --rm sdbkz-benchmark:ci \
    python3 scripts/q3329_verify.py --n 100 --beta 30 --seeds 1 --precision 1000
```

Full 100-seed reproduction (~8 CPU-hours on 22 workers, paper §8 headline):

```bash
docker run --rm -v "$PWD/results:/repo/results" sdbkz-benchmark:ci \
    python3 scripts/run_q3329_n100_local.py
```

Hardware independence established: the same seed produces bit-identical `get_r` values on Intel 13900K and AMD Zen 5 9950X3D (verified on seed 11). Aggregate rates match within sampling noise across the two vendors (Intel: 38.2% / 55 seeds; AMD: 37.8% / 45 seeds).

---

## Impact

### Affected
- Any `fplll` user running BKZ or LLL at `q ≥ O(2^12)` and `n ≥ 100`, regardless of `FT` type (double, long double, dpe, dd, qd, mpfr_t).
- The affected parameter surface explicitly includes **all post-quantum moduli tested so far**: ML-KEM / Kyber (q=3329), Dilithium (q=8380417), Saber (q=2^13), FrodoKEM (q=2^15) are expected to trigger the same pathology.

Sharp dimension onset (q=3329 β=30):

| `n`  | Degenerate seeds | Rate    |
|------|------------------|---------|
| 50   | 0 / 20           | 0.0%    |
| 70   | 0 / 20           | 0.0%    |
| 80   | 0 / 20           | 0.0%    |
| 90   | 1 / 20           | 5.0%    |
| 100  | 38 / 100         | **38.0%** |
| 110  | ≥22 / partial    | both algorithms affected every seed |

### Not affected

- `q = 97` at every dimension up to `n = 150`. The paper's main sweep (3,300 seeds) is entirely at `q = 97` and is verified clean.
- Non-cryptographic moduli small enough that `‖b_i‖²` and `Σ μ² · ‖b*_k‖²` do not overlap in magnitude.

### Not a precision bug

Increasing MPFR precision delays the symptom but does not fix it:
- 250-bit MPFR: visible GSO clamping in the active-block active region.
- 500-bit MPFR: per-tour d(LN) spikes of 100–300 nats.
- 1000-bit MPFR: **still 38% degeneracy at n=100 β=30**.

The root cause is arithmetic (loss of significance in a naive subtraction), not bit-width. Compensated summation is needed; more bits only delay the cancellation to a later tour.

---

## Mitigation

Replace the naive subtraction loop with a Kahan-compensated form:

```cpp
FT kahan_c, kahan_y, kahan_t;
kahan_c = 0.0;
for (int k = 0; k < j; k++)
{
  ftmp2.mul(mu(j, k), r(i, k));
  kahan_y.add(ftmp2, kahan_c);   // y = ftmp2 + c
  kahan_t.sub(ftmp1, kahan_y);   // t = ftmp1 - y
  kahan_c.sub(ftmp1, kahan_t);   // c = ftmp1 - t  (≈ y, off by lost bits)
  kahan_c.sub(kahan_c, kahan_y); // c = (ftmp1 - t) - y  (captured residual)
  ftmp1 = kahan_t;
}
r(i, j) = ftmp1;
```

The full patch is a single 30-line hunk at [`patches/fplll_gso_kahan.patch`](../../patches/fplll_gso_kahan.patch).

**Measured effect**: degeneracy rate drops from **38.0% (38/100 unpatched)** to **0% (0/55 patched)** at identical parameters (n=100, β=30, q=3329, 1000-bit MPFR). All 15 fplll regression tests (`make check`) pass. Patch applies cleanly to fplll HEAD commit `1987472` (2025-10-15) and to fplll 5.5.0 (vendored inside fpylll 0.6.4).

**Cost**: ~3× the inner-loop FP op count in the affected hot spot. Negligible at the outer-loop level since `update_gso_row` is amortised over a full tour. No change to the algorithm or public API.

**Precision**: no loss on `q = 97`. Bit-identical output verified across 55 patched vs 55 unpatched seeds at q=97 baseline parameters.

---

## Timeline

| Date       | Event                                                                                 |
|------------|---------------------------------------------------------------------------------------|
| 2026-04-02 | q=3329 instability first observed on cloud seeds; clamp hiding raw `get_r` for 9 days |
| 2026-04-10 | Direct `get_r` capture surfaces the negative squared norm. Cross-machine reproduction |
| 2026-04-10 | Kahan patch drafted and verified: 38% → 0% on 55-seed rerun, 15/15 `make check` pass  |
| 2026-04-15 | Patch shipped in repo as `patches/fplll_gso_kahan.patch` with README                  |
| 2026-04-18 | Draft upstream issue text prepared (maintained internally pre-filing)                 |
| TBD (gated on ePrint publication clearance)        | Upstream issue filed on fplll/fplll repo; target filing window is 7–14 days pre-publication    |
| TBD (gated on upstream issue + reviewer feedback)  | CVE status evaluated (likely N/A — numerical-correctness finding, not an exploitable vulnerability) |

Timeline entries are appended, never revised in place. Revision means a new row with `(revised YYYY-MM-DD: …)` annotation.

---

## Related upstream

- **[fpylll#272](https://github.com/fplll/fpylll/issues/272)** — floating-point exception for linearly dependent matrix (open since 2024-03-27). Same failure family: GSO pathology on near-degenerate input.
- **[fplll#237](https://github.com/fplll/fplll/issues/237)** — numerical stability tests (open since 2017-02-28). This finding is the kind of regression that issue asks for a test suite against.

---

## Evidence inventory

All artefacts are on-repo (no external hosting):

- [`paper/sdbkz_paper.pdf`](../../paper/sdbkz_paper.pdf) — §8 (pages 18–20): full characterization with 100-seed dataset, Wilson CI, BKZ-vs-SD-BKZ symmetry check, cross-machine rate comparison.
- [`patches/fplll_gso_kahan.patch`](../../patches/fplll_gso_kahan.patch) — single-hunk Kahan-compensation replacement.
- [`patches/README.md`](../../patches/README.md) — apply instructions, verification notes, scope statement.
- [`results/seeds/q3329/p1000_mt70/n100_beta30/`](../../results/seeds/q3329/p1000_mt70/n100_beta30/) — 100 lean seed JSONs + 45 fat companions (per-tour trajectories, Gram–Schmidt log-norms, RHF). SHA-256-indexed in `results/seed_manifest.json`.
- [`results/clamp_events.jsonl`](../../results/clamp_events.jsonl) — append-only log of every defensive clamp fire during the q=3329 campaign. Raw pre-clamp `get_r()` values preserved.
- [`hash_verification.txt`](../../hash_verification.txt) — cross-environment SHA-256 reconciliation.

---

## Classification: not a CVE

This is a numerical-correctness issue with cryptographic context, not an exploitable vulnerability. There is no attack vector that takes an external input and produces privilege escalation, data disclosure, or code execution. The concrete risk is:

> A lattice-based cryptographic parameter estimator that uses `fplll` to fit the Rankin profile at cryptographic moduli with `n ≥ 100` may silently produce reduction output whose d(LN) metric is contaminated by clamped or sign-flipped diagonal entries. The estimator could then either over- or under-estimate security margin depending on how it handles the anomaly.

Mitigation belongs upstream (fplll), not at the application layer. No downstream configuration change makes the cancellation go away short of applying this patch or equivalent.

If the estimator community disagrees with this classification, we'll revisit. CVE filing status will be recorded in the timeline section above.

---

## Contact

Findings or questions about this disclosure: **brendanchambersbou@gmail.com** (GPG key available on request). See also top-level [`SECURITY.md`](../../SECURITY.md) for the general reporting flow.
