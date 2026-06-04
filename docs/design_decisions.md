# Architecture decision records

Two significant structural decisions shaped the v1.2 / v1.3 code layout. Each is recorded here with the context that forced it, the decision that landed, and the consequences that followed.

Format is lightweight ADR — no strict template. Collapsed from an earlier 5-ADR scheme: at two decisions the one-file-per-ADR directory overhead exceeded the navigation benefit.

---

## ADR-001 — `_math_core` + `_bkz_core` split (v1.2.0)

**Status**: accepted, shipped 2026-04-18 via merge commit `c66160e` (tag `v1.2.0`).

### Context

A pre-v1.2 audit identified ~884 LOC of duplicated lattice-math and BKZ-driver code across six sibling sweep/verify scripts:

- `scripts/sweep_parallel.py`
- `scripts/sweep_cloud.py`
- `scripts/q3329_verify.py`
- `scripts/overnight_experiments.py`
- `scripts/run_3x_extended.py`
- `scripts/run_convergence_test.py`

Each maintained its own copy of `ln_fixed_point`, `build_lwe_kannan`, `metrics_from_gso`, `log_clamp` (defensive-clamp side-log helper), and a single-seed BKZ driver (`run_single`). The copies had drifted: different clamp-logging semantics, different `floor_mode` defaults, different schema-emit decisions (`store_per_tour` key appearance conditions).

The drift was not academic. It caused the 9-day q=3329 incident (narrative at [`incident_q3329_post_mortem.md`](incident_q3329_post_mortem.md)): one copy of the defensive clamp silently substituted a sentinel value without logging the raw pre-clamp `get_r()` return, while the other copy logged it. Draft paper §8 was written against the silent-clamp output, then had to be rewritten once the raw return was finally captured. Cost: ~9 days of debugging and a substantial §8 rewrite before submission.

### Decision

Extract the pure math + defensive-clamp helpers into `scripts/_math_core.py` as the single authoritative source:

- `ln_fixed_point(size, beta)` — Li–Nguyen Rankin profile, identical semantics to every legacy caller.
- `build_lwe_kannan(n, m, q, seed)` — deterministic lattice generator.
- `metrics_from_gso(M, dim, m, ln_profile, ...)` — post-tour metric extraction with clamp-event side-log.
- `log_clamp(ctx, position, raw_value, ...)` — one canonical defensive-clamp logger; writes raw pre-substitute values to `results/clamp_events.jsonl`.
- Named constants: `CLAMP_FLOOR_R = 1e-300` (sentinel for non-positive `get_r()` returns).

The BKZ driver itself goes into sibling `scripts/_bkz_core.py`:

- `run_single(n, beta, seed, q, precision, max_tours, log_clamp_fn, warn_on_clamp, store_per_tour, floor_mode, always_emit_store_per_tour)` — the canonical per-seed driver. Every variant-script wraps this with campaign-specific constants.
- Named constants: `STAGNATION_THRESHOLD = 1e-6`, `HEARTBEAT_EVERY = 25`, `CLAMP_FLOOR_R = 1e-300`.

The six legacy scripts now import from `_math_core` + `_bkz_core`; their local `run_single` functions became thin wrappers feeding the canonical driver campaign-specific arguments.

### Consequences

**Intended**:
- **Single source of truth**: every variant runs the same math. Drift is structurally impossible — changing `_math_core.metrics_from_gso` changes it for every caller, full stop.
- **Bit-identical output across the migration**: the v1.2-consolidation merge was gated on `scripts/confirm_v1_2.py` (30 seeds × 4 run_single paths, byte-compared to v1.1.0 baselines) and `scripts/test_math_core_parity.py` (576 comparisons across 6 legacy copies). 0 failures.
- **Faster onboarding**: a new reader follows one import chain (variant script → `_bkz_core.run_single` → `_math_core`) instead of re-reading the same ~150 lines in six files.
- **Defensive-clamp invariant concentrated in one place**: the "log raw value before substituting" discipline now lives at exactly one call site. Any future runner that wants clamp handling must use the shared helper; there is no second implementation to drift from.

**Accepted costs**:
- **One extra import hop** for readers tracing execution from a variant script. `sweep_parallel.run_single` now delegates to `_bkz_core.run_single`; readers see two layers. Documented in `CONTRIBUTING.md`; minor cost weighted against the drift elimination.
- **Slightly longer diffs for algorithm-level changes**: a single math edit now touches `_math_core` + (sometimes) a variant-script wrapper if the variant's thin shim needs updating. Ruff + pytest + the parity test keep this honest.
- **Variant-specific quirks preserved in wrapper kwargs**: `q3329_verify` wants `warn_on_clamp=True` and `always_emit_store_per_tour=True` for schema parity with its pre-v1.2 output; `sweep_parallel` uses `floor_mode="plain"` while `q3329_verify` uses `"safe"`. These are compatibility hooks, not regressions — called out in each wrapper's docstring.

### Verification artefacts

- `scripts/test_math_core_parity.py` — standalone 576-comparison parity check (60 `ln_fixed_point` pairs × 6 legacy copies + 36 `build_lwe_kannan` pairs × 6 legacy copies). Runs in ~0.2 s. 0 failures on v1.2.0 tree.
- `scripts/confirm_v1_2.py` — end-to-end 30-seed confirmation across 4 `run_single` paths, byte-compared against v1.1.0 baseline JSONs.
- `tests/test_math_core_edge_cases.py` — pytest suite covering clamp semantics, `log_clamp` schema, `ln_fixed_point` boundaries, `build_lwe_kannan` determinism, `metrics_from_gso` sensitivity to negative `get_r` values. 17 tests, ~0.2 s.

---

## ADR-002 — Seed manifest + campaign tree (v1.3.0)

**Status**: accepted, shipped 2026-04-18 via merge commit `17a1bef` (tag `v1.3.0`). Physical migration of 4,387 seeds landed in `ac52379`.

### Context

Pre-v1.3, seed JSONs lived under a half-dozen sibling directories:

```
results/raw/                         sweep_parallel local (q=97 main)
results/cloud/                       sweep_cloud S3 sync (q=97 main, cloud-run)
results/q3329/                       q=3329 mass dataset (n=50..100)
results/q3329_n70_beta30/            intermediate verification
results/q3329_n80_beta30/            intermediate verification
results/q3329_n90_beta30/            1000-bit n=90
results/cliff_500bit/                n=130 β=40 500-bit MPFR
results/fplll543_sensitivity/        fplll 5.4.3 variant
results/fplll544_sensitivity/        fplll 5.4.4 variant
results/fplll54_sensitivity/         fplll 5.4.5 variant
results/3x_tours/                    3× tour-budget runs
results/convergence/                 500-tour convergence
results/convergence_test/            follow-ups
results/q3329_degenerate/            clamp-event subset
```

Every new analysis pass re-discovered these dirs by grep or memory. Missing one meant silent under-counting in paper numbers. The 9-day q=3329 incident (see ADR-001 context) was partially caused by this scatter — the seed that triggered the investigation lived in a directory that the working analysis query did not traverse.

Two overlapping problems:

1. **Discoverability**: the next person (and future-me) had to know every legacy dir name. No documented complete list existed.
2. **No SHA-256 authority**: each analysis call rehashed on demand. A corrupted seed could survive multiple analysis passes before anyone noticed.

### Decision

Physically migrate every seed into a campaign-intent-organised tree:

```
results/seeds/
  main/            q97/n{n:03d}_beta{beta:02d}/seed{seed:04d}.json
  q3329/           p{precision}_mt{max_tours}/n{n:03d}_beta{beta:02d}/seed{seed:04d}.json
  cliff500/        q97/n{n:03d}_beta{beta:02d}/seed{seed:04d}.json
  fplll_sensitivity/ v{x_y_z}/q97/n{n:03d}_beta{beta:02d}/seed{seed:04d}.json
  tours3x/         q97/n{n:03d}_beta{beta:02d}/seed{seed:04d}.json
  convergence/     q97/n{n:03d}_beta{beta:02d}_mt{max_tours}/seed{seed:04d}.json
```

Each leaf directory pins exactly one `(campaign, n, β, q, precision, max_tours, fplll_version)` combination; the filename carries only the seed number. Campaign = intent of the run, not parameters (a q=97 seed from the cliff500 sweep belongs to `cliff500`, not `main`, regardless of matching parameter values).

Publish a verify-gated `results/seed_manifest.json` as the single authoritative index. Every entry carries `path + sha256 + size + mtime + n + beta + q + precision + max_tours + store_per_tour + advantage + tags + verified + verified_at_utc + verified_by`.

Cross-environment dual-copy preservation: the 205 `(n, β, seed)` triples present in both `results/raw/` (local VM) and `results/cloud/` (AWS Batch) from the paper's §3.7 cross-environment verification are kept as distinct files at the same leaf directory via a `_cloud` filename suffix (e.g. `seed0001.json` + `seed0001_cloud.json`). Both SHAs preserved.

Analysis code routes through `load_all_seeds(campaign="main")` (manifest query) instead of `load_all_seeds(*positional_dirs)` (legacy glob). A dual-mode shim keeps every pre-v1.3 caller working unchanged through back-compat symlinks at old paths; the symlinks drop at v2.0.0 per the design plan.

A CI gate (`scripts/lint_seed_manifest.py`) enforces three invariants on every push:

- **No orphans** — no file under `results/seeds/` missing from the manifest.
- **No ghosts** — no manifest entry pointing at a missing file.
- **No drift** (opt-in `--sha-check`) — on-disk SHA-256 matches the manifest record.

### Consequences

**Intended**:
- **Reviewer / collaborator navigation**: a cold `git clone` reader navigates to the right seed by stating campaign + parameters. No "which sub-directory did we forget?" failure mode.
- **SHA-256 as corruption detector**: every read can verify the manifest record. The CI lint runs the fast invariants on every push and the full `--sha-check` locally pre-tag.
- **Figure byte-identity preserved across the migration**: 14/14 paper PNGs SHA-256 identical pre- vs post-migration, verified by `diff` on the hash column (empty diff on the full v1.3 commit chain).
- **Forward-compat walker fix caught by v1.3.1**: when the overnight q=3329 fill landed seeds directly in the v1.3 tree (bypassing the legacy-dir → symlink path), the v1 walker missed them. Surfaced as 25 orphans under `lint_seed_manifest`; fixed in commit `2b5365c` by extending the walker to recurse `results/seeds/` natively with realpath-based dedup. Gap-caught-by-CI-gate, exactly the value the lint was designed to deliver.
- **Manifest schema is a referenced artefact**: `SECURITY.md` cites the `lint_seed_manifest` invariants as evidence-integrity policy; `docs/disclosure/fplll_gso_kahan_findings.md` cites the manifest as the SHA-256 authority. The manifest is not just an index — it's part of the security story.

**Accepted costs**:
- **Two layers during the v1.x transition**: backwards-compat symlinks at old paths coexist with the canonical v1.3 tree. Duplicated inodes, near-zero disk cost, clear extra cognitive load for any reader who notices the symlinks. Scheduled to drop at v2.0.0 (breaking layout change; see the v2.0.0 line in [`ROADMAP.md`](../ROADMAP.md)).
- **Campaign-intent mapping is a judgement call**: cloud-sourced q=3329 seeds remapped from `main` (where `sweep_cloud.py` originally filed them) to `q3329` (intent-aware). Documented inline in `scripts/build_seed_manifest.py`; called out in the manifest-build commit message. Low-risk when the judgement follows the paper's narrative; future reviewers can always regroup.
- **`paper/hash_verification.txt` paths still reference pre-v1.3 `results/raw/`**: preserved through v1.4 via symlinks. The `results/seed_path_crosswalk.csv` crosswalk is the permanent record; paper §9 will gain a one-sentence pointer at the v2.0.0 breaking change.

### Verification artefacts

- `tests/test_build_seed_manifest.py` — 21 tests: empty dir, single seed, fat+lean pair, schema reject, q-mismatch, fplll-version parse, 3x tag, SHA-256 identity, summarise, CLI idempotency, + 8 v1.3-native walker cases (direct-in-tree parse, symlink dedup, per-campaign path extraction for all 6 campaigns, unknown-campaign rejection).
- `tests/test_migrate_seeds_to_new_layout.py` — 20 tests: per-campaign `new_path_for` spec, fat-sibling co-location, dry-run idempotency, execute + crosswalk + symlinks, preflight (missing source, new-path collision), CLI smoke.
- `tests/test_seed_paths.py` — 18 parity tests against `migrate_seeds_to_new_layout.new_path_for()` across all 6 campaigns + edge cases (fat, cloud suffix, missing optional args).
- `tests/test_analysis_data_loader.py` — 10 tests: manifest filter combos, fat-skip default, non-cloud preference on collision, manifest-missing error, legacy dirs shim, min_seeds filter, load_json=False, cache invalidation on mtime change.
- `tests/test_lint_seed_manifest.py` — 10 tests: clean tree, orphan, ghost, drift (--sha-check only), manifest missing (exit 2), parse error (exit 2), symlink skip, allowlist, summary_ prefix, quiet mode.

Total manifest-related test surface: 79 tests; part of the 214-test suite that runs on every commit.

---

## ADR-003 — Multiple-comparison correction over the 33-cell main grid (v1.5.1)

**Status**: accepted, shipped 2026-05-14 on branch `phase1/holm-cliff`.

### Context

The v1.5.0 paper-claims artefact `results/paper_claims/full_stats_33groups.txt` reports per-group paired t-test and Wilcoxon p-values across the 33 (n, β) cells of the q=97 main sweep. Pre-v1.5.1 the table prints raw p-values only; no multiple-comparison correction is applied.

The 33-cell family is a paper headline table. A reviewer-grade reading wants strict family-wise error control: "given the 33 tests reported, what is the worst-case probability of at least one false positive at α = 0.05?" Without correction the bound is `1 − (1 − 0.05)^33 ≈ 0.81`, which is not defensible at the level of paper Section 4.

Two standard corrections are candidates:

- **Bonferroni / Holm step-down** — strict family-wise error rate (FWER) control. Holm dominates Bonferroni uniformly at no additional assumption.
- **Benjamini–Hochberg (BH)** — false discovery rate (FDR) control. Strictly less conservative; admissible when the cost of a false positive is symmetric with the cost of a false negative.

### Decision

Apply Holm step-down across the 33-cell family. Report both the raw and Holm-adjusted columns side-by-side in the paper headline table and in `analysis/stats_analysis.py` and `analysis/tables.py`.

The justification has three layers:

1. **Small family.** 33 tests is small enough that the Holm conservativeness penalty is bounded: even the worst-case Bonferroni factor of 33× barely moves cells with `p < 1e-30` (the median main-grid cell), while protecting the borderline cells (`p ≈ 1e-2` at n=120 β=20 and n=120 β=40) where the question genuinely matters.
2. **Asymmetric cost.** A false positive in a paper headline table is more expensive than an over-correction: the table is cited downstream, the over-correction column merely sits adjacent to the raw column, and any reader who prefers BH can derive it from the raw p-values they retain.
3. **No additional assumption.** Holm imposes no dependence-structure assumption on the p-values. BH requires independence or positive dependence; the (n, β) cells are computed from disjoint seed sets but the BKZ trajectories share the deterministic LWE-Kannan construction, so dependence is not provably benign.

Cohen's d alone is insufficient as an effect-size companion: it assumes the distribution is symmetric enough that mean / std is well-defined, which fails for cells where the advantage is sign-flipping (n=120, n=130 at β=20 sit near zero). Cliff's δ — `(#wins − #losses) / n_total` — is added alongside as the distribution-free counterpart. The two disagree when tail outliers inflate Cohen's d without moving the median; the paper now reports both so the asymmetry is visible.

### Consequences

**Intended**:
- The paper Section 4 table now carries a defensible α = 0.05 family-wise bound.
- Reviewer questions about multiple comparisons collapse to "the column is right there in the table."
- Cliff's δ surfaces effect-size sign and magnitude robustly even where Cohen's d is misleading.

**Accepted costs**:
- Table width grows by two columns. Acceptable.
- The Holm correction at this family size is conservative for cells with `p ≪ 0.01`. Acceptable — the cost is only in cells where the question is already settled.
- Cliff's δ requires interpretation against a different scale than Cohen's d (Romano et al.: negligible <0.147, small <0.33, medium <0.474, large otherwise). The script labels this inline.

**Not in scope**:
- Per-comparison correction over the full multi-campaign corpus (cliff500, q3329, convergence). The 33-cell family is the headline; the secondary campaigns are reported as standalone groups with their own significance discussions.
- Replacing Cohen's d. The two effect sizes are complementary, not redundant.

### Verification artefacts

- `analysis/_stats_helpers.py` — `cliffs_delta()` + `holm_bonferroni()` with module docstring citing this ADR.
- `tests/test_stats.py` — 19 pytest cases: Cliff's δ edge cases (all-win, all-loss, all-tie, empty, balanced, majority, ties, sign-match, range bound) + Holm correctness (monotonicity, input-order preservation, smallest-equals-Bonferroni-for-rank-1, cap-at-one, equal-p case, strict-dominance over Bonferroni, `None` pass-through, all-`None`, empty, family-of-one).
- `results/paper_claims/full_stats_33groups.txt` — regenerated with raw + Holm columns + Cliff's δ.

### Bit-identity gate vs v1.5.0 baseline

The v1.5.1 phase-1 task brief required *zero diff in pre-correction p-values vs v1.5.0*. Gate result:

- **29 of 33 cells**: pre-correction `mean`, `Cohen's d`, and `p_ttest` reproduce the v1.5.0 baseline within the baseline TXT rendering precision (3 decimal places on mean, 2 decimal places on Cohen's d, 3 significant figures on p). These are the cells whose seed count is unchanged at 100.
- **4 of 33 cells grew**: `n=100 β=30` (100 → 122 seeds), `n=100 β=40` (100 → 122), `n=110 β=40` (100 → 122), `n=130 β=40` (100 → 122). The +22 seeds per cell entered via the cliff-localisation sweeps that landed post-v1.5.0; the seed JSONs themselves are bit-identical to v1.5.0 *for the 100 seeds the baseline saw*, but the cell aggregate has shifted proportional to the added data (`Δmean ≤ 0.01`, `Δp` shifts strictly downward in significance — every grown cell remains `p < 1e-50`). This is corpus growth, not a code regression.
- **Precision caveat**: "bit-identical within baseline TXT rendering precision" is display-identity, not floating-point identity. The v1.5.0 paper-claims artefact was rendered with `f"{:.6f}"` for means, `f"{:.2f}"` for d, and `format_p()` which truncates p to a decade boundary below `1e-10`. The full-precision floats are not preserved in the v1.5.0 artefact, so a stricter byte-identity test is not possible against that file. A future v2-tier change would emit raw floats to a side JSON for round-tripable identity tests; out of scope here.

### Scope-creep note

The v1.5.1 phase-1 brief specified Cliff's δ + Holm columns. Mid-phase the script also gained a `--campaign <name>` argparse flag (default `main`) so that `stats_analysis.py` reads the v1.3 seed manifest by default rather than the legacy `results/raw/` directory. This was required because the v1.5.0 `full_stats_33groups.txt` artefact was generated from manifest-mode data (33 cells × ~100 seeds = 3300+), not from the `results/raw/` 22-cell subset. The legacy `--results-dir` flag continues to function unchanged. No paper claim or downstream consumer depends on the default-path change; the flag is additive and the prior call-form remains valid. Documented here so a future reader doesn't trip on the difference.

---

## ADR-004 — Docker base-image digest pinning + apt via snapshot.debian.org (v1.5.1)

**Status**: accepted, shipped 2026-05-14 on branch `phase2/docker-pins`.

### Context

The v1.5.0 reproducibility chain depends on two unanchored references in every Dockerfile:

1. **Base image** — `FROM python:3.12.3-bookworm`. Docker Hub stores the tag as a mutable pointer to a manifest digest; nothing prevents the upstream `python` image maintainers from republishing the tag with a new sha256 (security backports, glibc updates, etc.).
2. **apt-installed `libmpfr-dev` + `libgmp-dev`** — resolved against the *current* `deb.debian.org/debian` index at build time. Debian rolls package revisions independently of upstream-version changes; the original Dockerfile had pinned `libmpfr-dev=4.2.1-1` explicitly but had to drop the pin because Debian Bookworm bumped the package revision and the old apt version vanished from current mirrors. Re-pinning to a specific revision string sets up the same trap.

Either reference drifting silently invalidates the v1.5.x reproducibility claim without breaking the build — the seed SHA-256s would shift the next time someone rebuilt the image, and `verify.sh` would catch it only at the next CI cycle.

### Decision

Two complementary anchors:

1. **Digest-pin the base image** in all four Dockerfiles (`Dockerfile`, `Dockerfile.cloud`, `Dockerfile.fplll54`, `Dockerfile.fplll_legacy`) to `python:3.12.3-bookworm@sha256:25dee7f137aa44c4962d21346385737eb81954b6f06f519fcc348b67f6483d3c`. Resolved from the Docker Hub registry v2 API on 2026-05-14; tag `last_updated` 2024-05-14T18:08:59Z. The digest covers libmpfr6 4.2.0, libgmp10, glibc, Python 3.12.3, and every other runtime layer baked into the image.
2. **Pin apt via snapshot.debian.org** at date `20240614T000000Z` (one month after the base-image `last_updated`, ensuring the package set in apt matches the runtime libs the digest pin bakes in). Each Dockerfile's `RUN apt-get` step rewrites `/etc/apt/sources.list.d/debian.sources` to the snapshot mirror before the install. `Acquire::Check-Valid-Until=false` is set because snapshot archives serve expired `Valid-Until` headers by design (the snapshot index is frozen in time).

### Rejected option: vendor MPFR 4.2.1 source tarball + SHA-256

Considered: download `mpfr-4.2.1.tar.xz` from `https://www.mpfr.org/mpfr-current/`, verify against the upstream SHA-256, `./configure --prefix=/usr/local && make && make install` in the Dockerfile, set `LD_LIBRARY_PATH=/usr/local/lib` so fpylll links against the vendored MPFR.

Rejected because:
- The `fpylll==0.6.4` wheel on PyPI is pre-built and ships with its own libmpfr link (`libmpfr.so.6` from the wheel-build environment). A vendored `/usr/local/lib/libmpfr.so.6` is only used by the legacy variants (`Dockerfile.fplll54`, `Dockerfile.fplll_legacy`) that source-build fplll. For the main + cloud Dockerfiles the wheel never recompiles.
- Adds 5-10 min build time on every CI run for negligible benefit on the paper-cited image.
- The `libmpfr6` runtime that the wheel actually links against is already locked by the base-image digest pin in option 1.

### Consequences

**Intended**:
- A reviewer can byte-replay the base layer from the digest alone, without trusting that Docker Hub kept the tag stable. `docker pull python@sha256:25dee...` resolves identically across years.
- apt installs are reproducible against a fixed Debian archive snapshot regardless of mirror revision rolls.
- The `libmpfr-dev` / `libgmp-dev` install path is now reproducibility-anchored even for the source-built legacy variants (where the headers genuinely matter).

**Accepted costs**:
- `snapshot.debian.org` is rate-limited; CI builds may slow by ~30 s on the apt step.
- The Dockerfile comment block is longer; a reader needs to follow the digest provenance back to this ADR.
- Re-pinning to a new digest (e.g. for a Python 3.13 bump) becomes a two-step coordinated edit (digest + snapshot date), not a one-line tag change. Documented in `CONTRIBUTING.md` (out of scope here; deferred to opportunistic touch).

**Not in scope**:
- Vendor-tarball MPFR build (rejected above).
- Pinning `fpylll==0.6.4` to an upstream wheel sha256. Numerical-core pins (`fpylll`, `cysignals`, `numpy`) are off-limits per Phase 2 tasking; their pin path lives in `pyproject.toml` and is already version-locked. Adding a wheel-sha256 pin is a v2-tier concern.

### Verification artefacts

- `Dockerfile`, `Dockerfile.cloud`, `Dockerfile.fplll54`, `Dockerfile.fplll_legacy` — all four carry the digest pin + snapshot.debian.org sources rewrite at the same canonical date.
- `scripts/verify.sh` — header block records the digest + snapshot date so the reproducibility chain is self-describing.
- Dry-run gate: `docker build -t sdbkz:phase2-test .` against the modified Dockerfile, then `docker run --rm -e NUM_SEEDS=1 sdbkz:phase2-test bash scripts/verify.sh` returns `VERIFICATION PASSED` matching the 5 reference advantage values within the 1e-4 tolerance encoded in `verify.sh`.

## ADR-005 — G6K as a separate, single-threaded, SHA-locked sieve path (Phase 1)

**Status**: scaffolded 2026-06-04 on branch `generators-refactor`. Build + manifest only — no engine seam, no seeds, no science (those are Phase 2 / Phase 4). Reference SHA capture deferred to the first canonical build.

### Context

We want to add the G6K (General Sieve Kernel) lattice sieve as a second reduction engine alongside the fplll BKZ path, and hold it to the same SHA-256 byte-identity reproducibility bar the fplll path already meets (ADR-002, ADR-004).

Phase 0 recon (2026-06-04, `/tmp/g6k_phase0_report.md`) settled the blocker question empirically:

- **G6K is byte-reproducible only at `threads=1`.** At `threads=1`, fixing `FPLLL.set_random_seed(S)` before basis generation *and again immediately before the sieve* gives bit-identical reduced basis + GSO profile across repeated runs (seeded ×3 and even unseeded ×2 all matched). The sieve's sampler draws from fplll's global RNG, so the second FPLLL re-seed — not any g6k-level knob — is what fixes the sieve RNG. (`SieverParams["seed"]` is **not** a key in fpylll `e25ade8` / g6k `c71e084`: setting one is a silently-ignored no-op that emits `Attribute 'seed' unknown`, verified 2026-06-04 during the Phase 1 build. The contract was corrected to drop it; the reference SHA is identical with and without the inert line.)
- **Multi-threaded sieving is nondeterministic even with every seed pinned.** Seeded `threads=4` produced 4 distinct hashes across 4 runs; `threads=8` likewise. The nondeterminism is the *order of concurrent vector insertions* into the sieve database — a thread-scheduling race that no RNG seed controls. Thread count also shifts output (`t1≠t4≠t8`).
- A false-positive guardrail: at small size (dim 70 / blocksize 45) `t=4` matched `t=1` because the sieve DB was too small to actually parallelise; the real probe runs at dim 80 / blocksize 60 where the sieve genuinely threads.

### Decision

1. **Contract is `threads=1`, non-negotiable.** `g6k_probe.py` rejects `threads>1` with exit 3 rather than warning — an MT hash that got recorded would silently poison the reference. `lint_g6k_manifest.py` invariant (1) enforces `threads==1` on the contract, the reference, and every seed entry.
2. **Source-build, not the wheel.** `Dockerfile.g6k` source-builds fplll (@`1987472`) → fpylll (@`e25ade8`, reports 0.6.4) → g6k (@`c71e084`). The PyPI `fpylll` wheel bundles its own fplll and ships no headers, so G6K's C++ kernel cannot link against it. Base image digest-pinned + apt via snapshot.debian.org per ADR-004.
3. **`-march=x86-64-v3`, NOT `-march=native`.** Native bakes the build host's exact ISA and breaks cross-machine bit-identity. x86-64-v3 (AVX2/BMI2/FMA) is the common floor across the two target machines (Intel 13900K, AMD 9950X3D) and is the compilation target the contract pins. Phase 0 hashes were `-march=native` and are therefore **not** valid references here.
4. **Separate manifest, never merged.** `results/g6k_seed_manifest.json` is distinct from `results/seed_manifest.json`. The two engines produce non-comparable hashes; merging them would invite cross-engine confusion in any downstream SHA audit. `lint_g6k_manifest.py` invariant (3a) enforces disjointness of both `path` and `sha256` between the two manifests.
5. **Separate CI job.** `.github/workflows/build-and-verify.yml` gains a `g6k-build-and-verify` job independent of the fplll regression job, so a still-pending g6k reference cannot mask — and a g6k drift cannot be confused with — the fplll byte-identity proof.

### Why separate manifests (the merge temptation)

Both manifests carry `{path, sha256}` records and it is tempting to fold g6k seeds into the existing `seed_manifest.json` with an `engine` tag. Rejected: the fplll manifest's lint, schema (`docs/seed_manifest_schema.md`), validators, and the paper's reproducibility narrative all assume one engine. A g6k SHA sitting in that file would be compared, walked, and cited under fplll assumptions. Two files with an enforced-disjoint invariant is the honest separation — the hashes differ *by design* (different engine), and the lint makes that explicit rather than implicit.

### Capturing the reference

The reference SHA is `PENDING-FIRST-BUILD` in the manifest until a clean pinned build on a target machine fills it:

```
docker build -f Dockerfile.g6k -t sdbkz-g6k:ref .
docker run --rm sdbkz-g6k:ref python3 scripts/g6k_probe.py --n 80 --beta 60 --seed 42 --json
# paste basis_sha256 + rprof_sha256 into results/g6k_seed_manifest.json,
# set reference.captured_on, then:
python3 scripts/lint_g6k_manifest.py --sha-check --require-ref   # must be green
```

Then flip the CI g6k-verify step from PENDING-tolerant (exit 4 = warning) to a hard gate, and add `--require-ref` to the CI lint step.

### Consequences

**Intended**: G6K gains a byte-identity reproducibility gate matching the fplll path. The `threads=1` contract is machine-checked, not documentation-only.

**Accepted costs**: SHA-locking forces single-threaded sieving, discarding G6K's parallel-sieve throughput — the value/cost tradeoff of adopting G6K at all is a separate (Phase 2+) decision this ADR does not settle. Source-building three C/C++ projects adds ~8–10 min to the g6k CI job (mitigated by gha layer cache, `scope=g6k`).

**Not in scope**: the engine seam that lets the sweep dispatch to g6k (Phase 2); any g6k-reduced seeds (Phase 4); cross-machine reference confirmation (needs the second target machine).

### Verification artefacts

- `Dockerfile.g6k`, `scripts/g6k_probe.py`, `scripts/verify_g6k.sh`, `scripts/lint_g6k_manifest.py`, `results/g6k_seed_manifest.json` — the scaffold.
- `/tmp/g6k_phase0_report.md` — Phase 0 determinism recon (not committed; the SHA-table evidence behind the `threads=1` contract).
- Dry-run gate (Phase 1): `docker build -f Dockerfile.g6k --check .` lints the Dockerfile; `python3 scripts/lint_g6k_manifest.py` is green in scaffold state; `scripts/verify_g6k.sh` reports PENDING (exit 4) until the reference is captured.

---

## ADR-006 — Engine seam: g6k as a `_bkz_core` backend (Phase 2)

**Status**: Accepted (seam only; g6k production seeds NOT in scope — see Boundary).
**Date**: 2026-06-04.
**Supersedes scope note in ADR-005** ("the engine seam … is Phase 2") — this is that seam.

### Context

ADR-005 shipped g6k as a standalone, SHA-locked *probe* (`g6k_probe.py`), proving the single-threaded sieve is bit-reproducible — but disconnected from the science driver. The science runs through `_bkz_core.run_single`, which hard-coded fplll: one `BKZ.reduction(B, param, float_type="mpfr", precision=p)` per tour over an `IntegerMatrix`. To compare engines on the *same* lattices, the driver must be able to dispatch its per-tour reduction to either engine without the tour loop, stagnation bookkeeping, or metric extraction knowing which engine ran.

### Decision

1. **The seam is a per-tour reduction backend, not a forked driver.** `scripts/_engine_backends.py` exposes `make_backend(name, B_init, beta, variant, seed, precision)` returning an object with exactly `tour()` (advance one BKZ tour) and `gso()` (an `update_gso()`'d fpylll `MatGSO` for metrics). `run_single` gains one kwarg, `backend="fplll"`, and calls through this surface. The tour loop is written ONCE; only the engine varies. (Keeps the ADR-001 anti-duplication invariant — no second `run_single`.)

2. **fplll path is byte-identical, and that is the regression gate.** `_FplllBackend` rebuilds `BKZ.Param` per tour and returns a fresh `GSO.Mat(B)` per `gso()` call — the exact pre-seam call sequence. Gate: the post-seam `run_single` reproduces the committed per-seed JSON exactly, modulo the three wall-clock fields (`timestamp`, `bkz_time`, `sdbkz_time`); `scripts/verify.sh` stays green. Proven on (n=50,β=20) seeds 1/2/5.

3. **g6k path shares the probe's primitive, and that is its own gate.** `g6k_probe.py` now drives its sieve through `make_backend("g6k", …)`, so the `verify_g6k.sh` exact-SHA gate (cf22519d… / d4faf05a…, n=80 β=60 seed=42) covers the backend code. A drift in the backend trips the reference. Re-verified green after the refactor.

4. **g6k `sdbkz` raises, it does not alias.** g6k has no settled SD-BKZ analog. `_G6kBackend(variant="sdbkz")` raises `NotImplementedError` rather than silently running plain BKZ — aliasing would make the advantage metric (`bkz_final_dln - sdbkz_final_dln`) meaningless. Consequence: `run_single(backend="g6k")` cannot yet produce a full seed (it loops bkz→sdbkz and raises on the second variant). This is intentional: the seam is proven, the g6k SD science is deferred.

### Boundary (STOP — review gate, per the Phase 0/1 cadence)

Settled before any g6k seed is generated, NOT decided here:
- **g6k SD-BKZ semantics** — what "sdbkz" means for a sieve (or whether the comparison is reframed, e.g. bkz-only or a different second arm). Until then the advantage metric is fplll-only.
- **Multi-tour g6k determinism** — the backend re-seeds FPLLL once at construction, matching the *single-tour* probe. Re-seed-once vs re-seed-per-tour for N>1 tours is UNPROVEN; lock it (extend `g6k_probe.py` to a multi-tour SHA, or settle the policy in a Phase 3 ADR) before trusting any multi-tour g6k seed.

### Verification artefacts

- `scripts/_engine_backends.py` — the backend seam (fplll + g6k).
- `scripts/_bkz_core.py` — `backend` kwarg; tour loop now engine-blind.
- `scripts/g6k_probe.py` — refactored to drive the shared g6k backend.
- Gates (both green 2026-06-04, this machine): `verify.sh` value gate + exact-JSON regression check (fplll, byte-identical); `verify_g6k.sh` SHA gate (g6k, cf22519d…/d4faf05a… through the backend).

---

## ADR-007 — g6k multi-tour determinism (Phase 3, Gate 1)

**Status**: Accepted (Gate 1 of the g6k-science boundary). Gate 2 (SD-BKZ semantics) is still open — see Boundary.
**Date**: 2026-06-04.

### Context

ADR-005/006 locked g6k byte-identity for a **single** `pump_n_jump_bkz_tour` (the probe). Any real reduction is *N* tours, so before any g6k seed is generated the multi-tour determinism must be proven and the re-seed policy fixed. Open question: re-seed fplll's global RNG (the sieve sampler's source) ONCE before tour 1, or before EVERY tour?

### Experiment

`scripts/g6k_probe.py` gained `--tours N` and `--reseed {once,per-tour}` (the backend gained `_G6kBackend.reseed`). n=80, β=60, seed=42, threads=1, in `sdbkz-g6k:ref`:

| run | basis sha (16) | rprof sha (16) |
|-----|----------------|----------------|
| tours=1, once (regression) | `cf22519d529d243c` | `d4faf05a194bd7a3` | == ADR-005 reference |
| tours=3, once — run A | `ea44fb2367fbef29` | `5c060b3fde03bc30` |
| tours=3, once — run B | `ea44fb2367fbef29` | `5c060b3fde03bc30` |
| tours=3, per-tour — run A | `ea44fb2367fbef29` | `5c060b3fde03bc30` |
| tours=3, per-tour — run B | `ea44fb2367fbef29` | `5c060b3fde03bc30` |

### Decision

1. **Multi-tour g6k is deterministic.** Re-seed-once reproduces its own SHA bit-for-bit across independent runs at N>1 tours — `threads=1` is sufficient, as it is for the single tour. No new nondeterminism appears across tours.
2. **Re-seed policy = ONCE, at Siever construction** (the backend's existing behaviour). The question is empirically MOOT: `once` and `per-tour` produce **bit-identical** output. The seed set before the Siever is built fully determines all N tours; re-seeding fplll's global RNG mid-run does not reach the sieve's already-initialised sampler. Re-seed-once is also the natural policy (a normal reduction is not re-seeded mid-run). Do NOT add per-tour re-seeding — it is a no-op that would only invite confusion.
3. **Reproduce / regression-check** with `g6k_probe.py --n 80 --beta 60 --seed 42 --tours 3` (default `--reseed once`) → `ea44fb23…` / `5c060b3f…`. Not added to the manifest gate (the single-tour reference remains the CI SHA gate); this is an on-demand determinism tripwire documented here.

### Boundary (Gate 2 — still open, blocks g6k seeds)

**g6k SD-BKZ semantics — undecided.** fplll's `SD_VARIANT` (self-dual BKZ) has no stock g6k equivalent. Recon (2026-06-04): g6k HAS dual machinery — `SieverParams.dual_mode`, `g6k.temp_params(dual_mode=…)`, and a shipped `slide_tour` (Gama–Nguyen slide reduction, dual-aware). Options: (A) construct a self-dual pump-BKZ tour (primal + `temp_params(dual_mode=True)` pass) — the faithful analog, our construction, needs validation; (B) use stock `slide_tour` — rejected, slide ≠ SD, conflates the comparison; (C) reframe g6k as bkz-only — narrower, ships. Gate 1 (this ADR) is the prerequisite for all of them and is now cleared. ADR-008 will settle A vs C.

### Verification artefacts

- `scripts/g6k_probe.py` — `--tours` / `--reseed`; `scripts/_engine_backends.py` — `_G6kBackend.reseed`.
- The experiment table above (reproducible in `sdbkz-g6k:ref`).

---

## ADR-008 — g6k SD-BKZ semantics: self-dual pump-BKZ, validated vs fplll SD_VARIANT (Phase 3, Gate 2)

**Status**: Accepted. Closes the Phase-3 g6k-science boundary (Gate 1 = ADR-007 determinism; Gate 2 = this). g6k seeds are now unblocked.
**Date**: 2026-06-04.
**Chooses**: Option A (self-dual pump-BKZ) from ADR-007's A/B/C. B (stock `slide_tour`) rejected — slide reduction ≠ SD-BKZ, conflates the comparison. C (bkz-only) was the fallback; not needed.

### Construction

A g6k **self-dual tour** (`_G6kBackend(variant="sdbkz").tour()`) is a primal `pump_n_jump_bkz_tour` followed by a **dual** one run under `g6k.temp_params(dual_mode=not g6k.params.dual_mode)`. g6k's documented dual mode runs all operations on the dual basis with `l_bound`/`r_bound` reflected about `full_n/2` (siever.pyx) — the same mechanism g6k's own `slide_tour` uses for its dual pass. This mirrors fplll `BKZ.SD_VARIANT` (primal+dual per loop). The science driver's per-tour d(LN) is read from the primal MatGSO after the `temp_params` block exits (mode reverts), so the metric stays in primal coordinates.

### Why validation is end-to-end, not by-inspection

A single dual pass cannot be judged by eyeballing the **primal** GS profile — dual reduction optimises the dual, so a probe showed an ambiguous signal (tail rises = plausibly correct; slope steepens = looks wrong through a primal lens). Primal-profile heuristics are the wrong validator. Instead we validate the whole construction against the **established** engine: fplll `SD_VARIANT` is the ground truth.

### Validation (n=80, β=40, 3 tours, threads=1, same q-ary lattice; `sdbkz-g6k:ref`)

The cross-engine test is the **SD−BKZ delta**: g6k ≠ fplll numerically (sieve vs enum), but how SD changes the profile vs each engine's own BKZ must agree.

| metric | fplll (SD−BKZ) | g6k (SD−BKZ) | same direction |
|--------|---------------:|-------------:|:--------------:|
| head ln(r₀) | −0.01905 | −0.00760 | ✅ SD lowers head |
| tail ln(r_{n−1}) | +0.01226 | +0.02474 | ✅ SD raises tail |
| slope (head−tail)/n | −0.00039 | −0.00040 | ✅ SD flattens profile |

SD-BKZ's signature — **flatten the GS profile** (lower head, raise tail) — is reproduced by the g6k self-dual construction on all three metrics, with the slope-flattening magnitude essentially identical (−0.00039 vs −0.00040). The construction is a coherent self-dual reduction.

**Determinism:** the sdbkz path (2 pnj sub-tours, both threads=1) is reproducible — `de9978db…` across independent runs; ADR-007's multi-tour determinism covers it.

### Reviewer defensibility

The construction matches the established fplll SD-BKZ signature (above). Independent prior art exists — *"A New Self-dual BKZ Algorithm Based on Lattice Sieving"* (Springer, 978-981-99-9331-4_22): self-dual reduction via alternating primal/dual sieving passes, the same shape as this construction. Not required for the result (the fplll ground-truth match is the proof) but available as a citation / future exact cross-check.

### Consequences

- `_G6kBackend(variant="sdbkz")` is implemented (the ADR-006 `NotImplementedError` is removed); the g6k advantage metric (bkz vs sdbkz) is now meaningful.
- Both g6k boundary gates are cleared. g6k seed generation (DSD-onset comparison, SD vs BKZ, cross-engine vs fplll) is unblocked — pending the science-run scope decision (Phase 4).

### Verification artefacts

- `scripts/_engine_backends.py` — `_G6kBackend` sdbkz self-dual tour.
- Validation harness (cross-engine SD−BKZ delta + sdbkz determinism), reproducible in `sdbkz-g6k:ref`; the table above is its output.
