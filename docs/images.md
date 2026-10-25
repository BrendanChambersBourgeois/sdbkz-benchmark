# Docker images: tag → recipe

Every image tag named in `config/sweep.toml`, the worklists or the scripts,
the Dockerfile and build args that produce it, and the `make` target that
rebuilds it. The targets only build; nothing runs a container.

`make images` lists the targets. `make image-digests` prints the local image ID
and RepoDigests of every tag (read-only). All tags are local builds and never
pushed, so `RepoDigests` is empty and the image ID is the identifier to record.

| Tag | Dockerfile | Build args (beyond `HOST_UID`/`HOST_GID`) | Make target | Built from |
|---|---|---|---|---|
| `sdbkz-benchmark:ci` | `Dockerfile` | none | `image-benchmark-ci` | HEAD recipe (`Dockerfile` last changed `a3ea230d`) |
| `sdbkz-g6k:ref` | `Dockerfile.g6k` | defaults (dim 128, `APPLY_INC63=1`) | `image-g6k-ref` | see note 1 |
| `sdbkz-g6k:ci` | `Dockerfile.g6k` | defaults; CI passes the runner's UID/GID | `image-g6k-ci` | built by `build-and-verify.yml` on each run |
| `sdbkz-g6k:dim256` | `Dockerfile.g6k` | `G6K_MAX_SIEVING_DIM=256` | `image-g6k-dim256` | see note 1 |
| `sdbkz-g6k:dim384` | `Dockerfile.g6k` | `G6K_MAX_SIEVING_DIM=384 APPLY_INC63=0` | `image-g6k-dim384` | `Dockerfile.g6k` at `f65c5415` (unpatched kernel) |
| `sdbkz-g6k:dim384-inc63` | `Dockerfile.g6k` | `G6K_MAX_SIEVING_DIM=384 APPLY_INC63=1` | `image-g6k-dim384-inc63` | `Dockerfile.g6k` at `ff108a7c` |
| `sdbkz-g6k:dim384-reject` | `Dockerfile.g6k` | `G6K_MAX_SIEVING_DIM=384 APPLY_INC63=1 REJECT_OVERFLOW=1` | `image-g6k-dim384-reject` | `Dockerfile.g6k` at `596db8e0` |
| `sdbkz-fplll-patched:kahan-v3` | `Dockerfile.fplll_patched` (removed from tree, see note 2) | `GSO_PATCH=patches/fplll_gso_kahan.patch` (removed from tree) | none (see note 2) | `Dockerfile.fplll_patched` at `e4c38ba0` |
| `sdbkz-fplll-patched:reorder-control` | `Dockerfile.fplll_patched` (removed from tree, see note 2) | `GSO_PATCH=patches/fplll_gso_reorder_control.patch` (removed from tree) | none (see note 2) | `Dockerfile.fplll_patched` at `e4c38ba0` |
| `sdbkz-fplll54` | `Dockerfile.fplll54` | none | `image-fplll54` | HEAD recipe |
| `sdbkz-fplll-patched:val2` | `Dockerfile.fplll_patched` (removed from tree, see note 2) | default `GSO_PATCH` at the time | none (retired) | see note 2 |

Build args were read back from `docker history` of the local images where
the image still exists (`dim384-inc63`, `kahan-v3`, `reorder-control`,
`benchmark:ci`).

## `APPLY_INC63`

`Dockerfile.g6k` applies `patches/g6k_gauss_nonimproving_tolerant.patch`
when `APPLY_INC63=1` (the default, and the behaviour since `ff108a7c`) and
skips it when `APPLY_INC63=0`. Any other value fails the build. Between
`f65c5415` (the recipe `dim384` was built from) and HEAD, the non-comment
changes to `Dockerfile.g6k` are the patch `COPY`s, the `APPLY_INC63` and
`REJECT_OVERFLOW` args and their `case` blocks; with `APPLY_INC63=0
REJECT_OVERFLOW=0` the build runs the old commands, so `image-g6k-dim384`
rebuilds the same kernel as the original `dim384`. The patch
file is still copied into `/tmp` with `APPLY_INC63=0`; the build does not use it.

## `REJECT_OVERFLOW`

With `REJECT_OVERFLOW=1` (needs `APPLY_INC63=1`) the build also applies
`patches/g6k_gauss_reject_overflow.patch`, which refuses a reduction in
`gauss_no_upd_reduce_in_db` or `reduce_in_db` whose int16 coefficients would
overflow instead of storing the wrapped vector. Sieving contexts of 50 and
above run the default hk3 sieve, which the patch does not change.
The default `0` leaves every other tag's build unchanged; any other value fails
the build.

## Notes

1. `ref` and `dim256` were first built before the x86-64-v2 target and
   `--disable-native` (`d6d05669`, `f65c5415`) and before the tolerant gauss_sieve patch.
   The make targets rebuild the HEAD recipe. For the original binary, build
   `Dockerfile.g6k` from `f3cda9c8` with the same args.
2. The patched fplll images (`kahan-v3`, `reorder-control`, `val2`) were built
   against q=3329 floors that came from our double-precision measurement GSO,
   not from fplll (Paper 2, Appendix A). `Dockerfile.fplll_patched`, the
   patches and their make targets left the tree on 2026-10-13 and exist only
   in git history: the `kahan-v3` and `reorder-control` recipes and targets at
   `78f43c95`, and the `val2` recipe at `e6ab69d5` with
   `patches/fplll_gso_kahan.patch` from `161f1880` (the pre-`28b6c650` patch,
   whose compensation sign is flipped). No new runs use these images.
3. A rebuild reproduces the recipe, not the image ID, because layer timestamps
   differ. The acceptance test for a rebuild is the image's own gate:
   `scripts/verify_g6k.sh` against `results/g6k_seed_manifest.json` for g6k
   images.
4. Pins: `Dockerfile.g6k` pins fplll, fpylll and g6k by commit.
5. The Steam Machine node runs its own podman build of `dim384-inc63`. Its
   image ID is not recorded here.
