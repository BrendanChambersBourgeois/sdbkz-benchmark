# Patches

Out-of-tree patches applied by the Docker recipes. Not part of the benchmark core.

The fplll Gram–Schmidt patches (`fplll_gso_kahan.patch`, its tests diff and `fplll_gso_reorder_control.patch`) left the tree on 2026-10-13: the q=3329 floors they targeted came from our double-precision measurement GSO, not from fplll (Paper 2, Appendix A). Git history keeps them (`78f43c95`).

## `g6k_gauss_nonimproving_tolerant.patch`

**Later finding:** the trigger is int16 coefficient overflow in the in-db reduction, not float32 prediction error; a wrapped vector can then repeat the same non-improving swap indefinitely. See `g6k_gauss_reject_overflow.patch` below. The text in this section predates that.

Tolerant handling of non-improving in-database reductions in G6K's `kernel/sieving.cpp`
`gauss_sieve`. Applies to g6k commit `c71e084`.

**Symptom:** every NTRU β=60 seed at n∈{179,181} (9/9 attempts, both compute nodes) and 2 of
~1300 β=50 seeds abort 65–109 minutes in with `RuntimeError: Aborted` (cysignals-translated
SIGABRT). journald shows the cause:

```
python3: sieving.cpp:118: void Siever::gauss_sieve(std::size_t): Assertion `cv2_vec_len > fast_cdb[j].len' failed.
```

**Root cause:** `gauss_no_upd_reduce_in_db` accepts a reduction when the PREDICTED new length
(cached float32 lengths + a float32 inner product of cached `yr` coordinates) beats
`REDUCE_LEN_MARGIN` (1.01), but then stores the exactly RECOMPUTED length
(`recompute_data_for_entry`), which can be arbitrarily larger — a diagnostic build
measured `old_len=183593.9 → new_len=13861248` (75.5×, both finite) at sieve context 49 on the
crashing seed. This is float32 prediction breakdown at large-norm NTRU cells, not marginal
rounding. The bgj1 and bdgl
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
verdict confirmed by a diagnostic image (`GAUSS_ASSERT_DUMP` build): both lengths
finite, recomputed 75.5× the pre-reduction length — prediction breakdown, not NaN poisoning.
Determinism SHA gate (`verify_g6k.sh`) passes bit-exact on the patched image.

## `g6k_gauss_reject_overflow.patch`

Applied **after** `g6k_gauss_nonimproving_tolerant.patch` (g6k commit `c71e084`). G6K stores
coefficients as int16 (`ZT`), and `addsub_vec` wraps a sum outside the int16 range, so the
stored vector is no longer the one whose length the reduction test accepted. The patch checks
the coefficient sum before `addsub_vec` in `gauss_no_upd_reduce_in_db` and `reduce_in_db` and
refuses the reduction if any coefficient would leave [-32767, 32767]. Rejections are counted and
the count is reported on stderr at powers of two; nothing is substituted silently. Sieving contexts
of 50 and above run the default hk3 sieve, which this patch does not change.

Wired into `Dockerfile.g6k` behind `REJECT_OVERFLOW=1` (default `0`); image
`sdbkz-g6k:dim384-reject` (`make image-g6k-dim384-reject`). Local, not filed upstream.
