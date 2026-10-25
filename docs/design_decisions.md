# Architecture decision records

One entry per structural decision: what was decided and why. Verification lives in `tests/` and the CI workflow.

**ADR-001 (v1.2.0) — shared numerical core.** All runners call `scripts/_bkz_core.py::run_single`, which calls `scripts/_math_core.py` for metrics and the defensive-clamp side-log. Why: six runners carried copies of the same ~150 lines and drifted. Gated by a byte-identical comparison of 30 seeds across four run paths against v1.1.0.

**ADR-002 (v1.3.0) — seed manifest and campaign tree.** Every seed lives under `results/seeds/<campaign>/q<q>/p<precision>_mt<tours>/n<n>_beta<β>/` and is indexed in `results/seed_manifest.json` with SHA-256, size and verified flag. Writers go through `scripts/_seed_paths.py`, readers through the manifest. Why: directory-glob loading silently mixed campaigns and precisions. `scripts/lint_seed_manifest.py` enforces no orphans, no ghosts, no hash drift. Legacy paths map through `results/seed_path_crosswalk.csv` (symlinks removed at v2.0.0).

**ADR-003 (v1.5.1) — multiple-comparison correction.** Holm step-down across the 33-cell main grid; raw and adjusted p-values reported side by side. Why: 33 paired tests at α=0.05 need a family-wise correction, and Holm is uniformly more powerful than Bonferroni without independence assumptions.

**ADR-004 (v1.5.1) — pinned images.** Base image by digest, apt via a dated snapshot.debian.org archive. Why: a tag or a package revision can move under a build; the digest and the snapshot cannot. Vendoring an MPFR tarball was rejected as a second build path to maintain.

**ADR-005 — G6K as a separate engine.** `Dockerfile.g6k` source-builds fplll, fpylll and G6K at `-march=x86-64-v2 --disable-native`. G6K runs at `threads=1` only (multi-threaded sieving is non-deterministic: concurrent database insertion order). Its seeds have their own tree and manifest, `results/g6k_seed_manifest.json`, with an exact-SHA reference probe gated in CI by `verify_g6k.sh`. Why separate manifests: the engines' hashes are not comparable, and merging would invite cross-engine confusion in any later audit.

**ADR-006 — engine seam.** `scripts/_engine_backends.py::make_backend` gives `_bkz_core.run_single` a per-tour reduction backend (`fplll` or `g6k`) instead of a forked driver. Why: one driver, one metric path, one seed schema for both engines; the fplll path stays byte-identical.

**ADR-007 — multi-tour G6K determinism.** Re-seeding once reproduces the multi-tour SHA bit-for-bit at `threads=1`; no per-tour re-seed is needed. Measured before any G6K seed was written.

**ADR-008 — G6K self-dual variant.** Self-dual pump-BKZ built from G6K's dual machinery, validated end to end against fplll's `SD_VARIANT` on the same q-ary lattice (n=80, β=40, 3 tours) rather than by code inspection. Why: the construction is ours, so only an agreement test against the reference implementation makes it defensible.
