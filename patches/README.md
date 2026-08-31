# Patches

Out-of-tree patches referenced by the paper. Not part of the benchmark core — apply only if you need the described fix.

## `fplll_gso_kahan.patch`

Kahan-compensated subtraction in `fplll/gso_interface.cpp` (function `MatGSOInterface<ZT,FT>::update_gso_row`). Addresses the catastrophic-cancellation bug in fplll's squared-form GSO recurrence described in **§8 of the paper**.

**Symptom:** at `q=3329`, `n=100`, `β=30`, MPFR=1000 bits, 38% of seeds produce a degenerate final basis where one Gram–Schmidt log-norm crashes to the precision floor (~−345). Root cause: the diagonal update

```
r(i,i) = ‖b_i‖² − Σ_{k<i} μ(i,k)² · ‖b*_k‖²
```

is computed as a naive in-place subtract loop with no compensation, reorthogonalisation, or sign check. When `b_i` is nearly in the span of preceding `b*_k` — exactly the regime BKZ drives the basis into — the two large positive operands cancel and the residual loses precision, occasionally flipping sign.

**Fix:** replace the naive loop with a Kahan-compensated subtraction that maintains a running residual and folds the low-order bits lost on each step back into the accumulator. Code only — no test files, so the patch touches just `fplll/gso_interface.cpp` and `fplll/gso_interface.h`.

**Measured effect:** degeneracy rate drops from 38.0% (38/100 unpatched) to 0% (0/55 patched) at the same parameters. Passes all 15 fplll regression tests (`make check`) unchanged.

## `fplll_gso_kahan_tests.patch`

Optional regression test, kept in a separate diff so the code fix above stays test-free. Adds `tests/test_gso_kahan.cpp` (+ the `tests/Makefile.am` wiring): two near-degenerate bases on which the plain subtraction leaves a nonpositive `r(i,i)` (min `r = -0.625` and `-2.125`) with the `double` backend, while the compensated form keeps every GS norm positive. Fixtures hold under FMA contraction of the mul/sub pair. With this applied, `make check` runs 16/16.

Apply **after** `fplll_gso_kahan.patch`.

### Applying

```
git clone https://github.com/fplll/fplll.git
cd fplll
git checkout 1987472            # fplll HEAD as of 2025-10-15, verified 15/15 make check pass
git apply /path/to/sdbkz-benchmark/patches/fplll_gso_kahan.patch
git apply /path/to/sdbkz-benchmark/patches/fplll_gso_kahan_tests.patch   # optional
./autogen.sh && ./configure && make && make check
sudo make install
```

Also verified against fplll **5.5.0** (the version vendored inside fpylll 0.6.4, used by the paper's Docker build on 2026-04-10). Newer fplll HEADs may re-apply cleanly but have not been tested.

Rebuild fpylll against the patched fplll afterwards.

### Status

This is a **new instance** of an already-open failure family in fpylll/fplll (related: fpylll #272). It was filed upstream as [fplll PR #550](https://github.com/fplll/fplll/pull/550) (2026-05-08) and closed unmerged by the maintainer (2026-05-17); the corrected patch is now kept **local to this repo** — applied out-of-tree against a stock fplll checkout, not resubmitted or reopened. Maintained on the local fork branch `fix/gso-kahan-cancellation` as two commits (code fix, then the test), clang-format 18 clean. If you ship the patch in a downstream distribution, cite the paper.

All `q=97` results in the paper are unaffected and do not require this patch. Only `q=3329` (and presumably other cryptographic moduli at `n≥100`) trigger the cancellation.

## `g6k_gauss_nonimproving_tolerant.patch`

Tolerant handling of non-improving in-database reductions in G6K's `kernel/sieving.cpp`
`gauss_sieve` (INC-63, 2026-08-31). Applies to g6k commit `c71e084`.

**Symptom:** every NTRU β=60 seed at n∈{179,181} (9/9 attempts, both compute nodes) and 2 of
~1300 β=50 seeds abort 65–109 minutes in with `RuntimeError: Aborted` (cysignals-translated
SIGABRT). journald shows the cause:

```
python3: sieving.cpp:118: void Siever::gauss_sieve(std::size_t): Assertion `cv2_vec_len > fast_cdb[j].len' failed.
```

**Root cause:** `gauss_no_upd_reduce_in_db` accepts a reduction when the PREDICTED new length
beats `REDUCE_LEN_MARGIN` (1.01), but then stores the exactly RECOMPUTED length
(`recompute_data_for_entry`), which can round to ≥ the pre-reduction length. The bgj1 and bdgl
sieves re-validate after recompute (`REDUCE_LEN_MARGIN_HALF` check in `bgj1_replace_in_db` /
bdgl equivalent) and reject; the gauss path instead asserts the improvement it never re-checked.
The assert is compiled in because the source build does not define NDEBUG. Small sieve contexts
(35 at β=50, 44 at β=60, both below `gauss_crossover=50`) route every pump sieve call through
`gauss_sieve`, so the exposure is largest exactly at bumped-β NTRU wall cells.

**Fix:** capture the pre-reduction length on the candidate branch, and replace the assert with
the NDEBUG-equivalent tolerant swap plus a counter and a rate-limited stderr report (first 5
events, then every 4096th) including both lengths and their finiteness — never a silent
substitution. No algorithmic change on any run that previously completed: a seed that took the
failing branch aborted, so completed seeds never exercised it and reference SHAs are expected to
carry over (verify_g6k.sh decides).

### Applying

```
git clone https://github.com/fplll/g6k.git
cd g6k
git checkout c71e084
git apply /path/to/sdbkz-benchmark/patches/g6k_gauss_nonimproving_tolerant.patch
autoreconf -i && ./configure --disable-native --with-max-sieving-dim=384
pip install --no-build-isolation .
```

Wired into `Dockerfile.g6k` (COPY + `git apply` before `autoreconf`).

### Status

Local to this repo, out-of-tree against a stock g6k checkout; not filed upstream. Root-cause
verdict (recompute-roundoff vs non-finite lengths) confirmed by the INC-63 diagnostic image
(`GAUSS_ASSERT_DUMP` build) before this patch ships into any measured run.
