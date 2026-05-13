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

Total manifest-related test surface: 79 tests; part of the 96-test suite that runs on every commit.

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
