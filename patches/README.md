# Patches

Out-of-tree patches referenced by the paper. Not part of the benchmark core — apply only if you need the described fix.

## `fplll_gso_kahan.patch`

Kahan-compensated subtraction in `fplll/gso_interface.cpp` (function `MatGSOInterface<ZT,FT>::update_gso_row`). Addresses the catastrophic-cancellation bug in fplll's squared-form GSO recurrence described in **§8 of the paper**.

**Symptom:** at `q=3329`, `n=100`, `β=30`, MPFR=1000 bits, 38% of seeds produce a degenerate final basis where one Gram–Schmidt log-norm crashes to the precision floor (~−345). Root cause: the diagonal update

```
r(i,i) = ‖b_i‖² − Σ_{k<i} μ(i,k)² · ‖b*_k‖²
```

is computed as a naive in-place subtract loop with no compensation, reorthogonalisation, or sign check. When `b_i` is nearly in the span of preceding `b*_k` — exactly the regime BKZ drives the basis into — the two large positive operands cancel and the residual loses precision, occasionally flipping sign.

**Fix:** replace the naive loop with a Kahan-compensated subtraction that maintains a running residual and folds the low-order bits lost on each step back into the accumulator.

**Measured effect:** degeneracy rate drops from 38.0% (38/100 unpatched) to 0% (0/55 patched) at the same parameters. The patch passes all 15 fplll regression tests (`make check`).

### Applying

```
git clone https://github.com/fplll/fplll.git
cd fplll
git checkout 1987472            # fplll HEAD as of 2025-10-15, verified 15/15 make check pass
git apply /path/to/sdbkz-benchmark/patches/fplll_gso_kahan.patch
./autogen.sh && ./configure && make && make check
sudo make install
```

Also verified against fplll **5.5.0** (the version vendored inside fpylll 0.6.4, used by the paper's Docker build on 2026-04-10). Newer fplll HEADs may re-apply cleanly but have not been tested.

Rebuild fpylll against the patched fplll afterwards.

### Status

This is a **new instance** of an already-open failure family in fpylll/fplll (related: fpylll #272, fplll #237). It is **not upstreamed** — the paper author has reserved the option to file upstream separately. If you ship the patch in a downstream distribution, cite the paper.

All `q=97` results in the paper are unaffected and do not require this patch. Only `q=3329` (and presumably other cryptographic moduli at `n≥100`) trigger the cancellation.
