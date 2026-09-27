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
| `sdbkz-fplll-patched:kahan-v3` | `Dockerfile.fplll_patched` | `GSO_PATCH=patches/fplll_gso_kahan.patch` | `image-fplll-kahan-v3` | `Dockerfile.fplll_patched` at `e4c38ba0` |
| `sdbkz-fplll-patched:reorder-control` | `Dockerfile.fplll_patched` | `GSO_PATCH=patches/fplll_gso_reorder_control.patch` | `image-fplll-reorder-control` | `Dockerfile.fplll_patched` at `e4c38ba0` |
| `sdbkz-fplll54` | `Dockerfile.fplll54` | none | `image-fplll54` | HEAD recipe |
| `sdbkz-fplll-patched:val2` | `Dockerfile.fplll_patched` | default `GSO_PATCH` at the time | none (retired) | see note 2 |

Build args were read back from `docker history` of the local images where
the image still exists (`dim384-inc63`, `kahan-v3`, `reorder-control`,
`benchmark:ci`).

## `APPLY_INC63`

`Dockerfile.g6k` applies `patches/g6k_gauss_nonimproving_tolerant.patch`
when `APPLY_INC63=1` (the default, and the behaviour since `ff108a7c`) and
skips it when `APPLY_INC63=0`. Any other value fails the build. Between
`f65c5415` (the recipe `dim384` was built from) and HEAD, the only non-comment
change to `Dockerfile.g6k` is the patch `COPY` and `git apply`, so
`image-g6k-dim384` rebuilds the same kernel as the original `dim384`. The patch
file is still copied into `/tmp` with `APPLY_INC63=0`; the build does not use it.

## Notes

1. `ref` and `dim256` were first built before the x86-64-v2 target and
   `--disable-native` (`d6d05669`, `f65c5415`) and before the INC-63 patch.
   The make targets rebuild the HEAD recipe. For the original binary, build
   `Dockerfile.g6k` from `f3cda9c8` with the same args.
2. `val2` carries the pre-`28b6c650` Kahan patch, whose compensation sign is
   flipped. To rebuild it for audit, use `Dockerfile.fplll_patched` at
   `e6ab69d5` with `patches/fplll_gso_kahan.patch` from `161f1880`. No new runs
   use it.
3. A rebuild reproduces the recipe, not the image ID, because layer timestamps
   differ. The acceptance test for a rebuild is the image's own gate:
   `scripts/verify_g6k.sh` against `results/g6k_seed_manifest.json` for g6k
   images, and `make check` inside the build for `fplll_patched`.
4. Pins: the fplll source in `Dockerfile.fplll_patched` is pinned to commit
   `a8dedce384689047daba154bd50d6215e35bf03b` (the commit tag `5.5.0` points
   to). fpylll is still pinned to tag `0.6.4` until its commit can be resolved.
   `Dockerfile.g6k` pins fplll, fpylll and g6k by commit.
5. The Steam Machine node runs its own podman build of `dim384-inc63`. Its
   image ID is not recorded here.
