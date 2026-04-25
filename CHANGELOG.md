# Changelog

User-visible and structural changes to the SD-BKZ benchmark project.
Roughly [Keep a Changelog](https://keepachangelog.com/) style. Newest
release at the **top**.

## Format

```
## [version] — YYYY-MM-DD
### Added
- New features, scripts, datasets

### Changed
- Modifications to existing behavior

### Fixed
- Bug fixes that affect downstream users

### Removed
- Deprecated or deleted functionality
```

Versions follow loose SemVer. Bump on:
- **Major** — breaking schema changes, repo rename, paper submission tag
- **Minor** — new features, new sweep dimensions, new analysis scripts
- **Patch** — bug fixes, infra tweaks, doc updates

## Unreleased

### Added
- **`scripts/seed_timing.py`** (new library) — sweep wall-time
  estimator with two prediction methods (naive per-tour-cost and
  anchored to a completed reference run) and a recommendation
  between them. Returns a `SweepEstimate` dataclass carrying both
  predictions, p95 + median-absolute-deviation spread, anchor
  metadata (`(n,β,max_tours)`, age in days, source paths, last
  numerical-hotspot commit SHA), and a `notes` tuple of caveats.
  Anchor staleness gate: if the youngest anchor seed is older than
  the configurable threshold (default 7 d), the recommendation
  flips to naive and a warning enumerating the age + last commit
  SHA touching `scripts/_bkz_core.py` / `scripts/_math_core.py`
  is appended to `notes`. Cache-aware
  (`results/paper_claims/per_tour_cost_table.json`, mtime-validated;
  silently rebuilt on stale). Library-only — no main entry; added
  to `scripts/lint_logging.py` EXEMPT with inline justification.
  Foundational commit; CLI wrapper, cache-write integration into
  `build_seed_manifest.py`, and dispatcher hook in
  `run_convergence.py` ship in follow-up commits.
- **`tests/test_seed_timing.py`** (new) — 16 pytest cases covering
  table parsing, cache round-trip + freshness gate, anchor selection,
  age-warning behaviour, naive arithmetic, pool oversubscribe scaling,
  and graceful degradation on missing data. Synthetic fixtures only;
  never reads `results/seeds/`.
- **`tests/fixtures/synthetic_seeds/`** (new dir) — 5 minimal valid
  seed JSONs used by `test_seed_timing`. Two `(50, 20, 70)` plus two
  `(60, 30, 70)` plus one `(90, 30, 500)` anchor candidate.
- **`scripts/build_seed_manifest.py`** — added
  `_refresh_per_tour_cost_cache()` side-effect helper called once
  after a successful manifest write. Computes the per-(n, β)
  median per-tour cost from the seed corpus and writes
  `results/paper_claims/per_tour_cost_table.json` for fast
  consumption by `scripts/seed_timing`. Strictly post-manifest and
  isolated under narrow `try/except (FileNotFoundError, OSError,
  json.JSONDecodeError, KeyError, ValueError, TypeError, ImportError)`
  with a `WARNING` log on failure — cache failures degrade the
  estimator only, never block the manifest write or paper-safety
  SHA chain. `seed_timing` is lazy-imported inside the helper so a
  broken/absent estimator can never propagate to manifest rebuild.
- **`scripts/run_convergence.py`** — dispatcher now emits an ETA
  prediction at sweep launch. After argparse + run_id assignment,
  the runner lazy-imports `seed_timing`, calls `estimate_sweep_wall`
  with the resolved pool shape, and folds
  `predicted_wall_h_naive`, `predicted_wall_h_anchored`,
  `predicted_wall_h_p95`, `method_recommended`, `anchor_used`, and
  `anchor_age_days` into the existing `dispatch` event ctx in
  `logs/pipeline.jsonl`. Operators see the ETA in the launch log
  line; jq queries can later reconcile predicted-vs-actual after
  the sweep completes. Estimator failure is non-fatal — narrow
  `try/except (ImportError, FileNotFoundError, OSError, KeyError,
  ValueError, TypeError)` logs a WARNING and the sweep launches
  with the dispatch event minus the ETA fields. Currently-running
  sweeps are unaffected (forked bytecode).
- **`scripts/estimate_sweep_time.py`** (new CLI) — argparse wrapper
  around `seed_timing` for ad-hoc sweep planning. Required:
  `--n --beta --max-tours`. Optional: `--seeds`, `--workers`,
  `--cache-path`, `--no-cache`, `--anchor-age-warn-days`. Pretty
  human report to stderr + a single structured `estimate` event to
  `logs/pipeline.jsonl` under `cat="estimator"` (filterable via
  `jq 'select(.cat == "estimator")'`). Always exits 0 — advisory,
  never blocks anything.

## [1.5.0] — 2026-04-22

Tag: `v1.5.0`. Repo flipped private → public. First Zenodo DOI:
`10.5281/zenodo.19686928` (concept DOI, resolves to latest
version). Release notes at
https://github.com/BrendanChambersBourgeois/sdbkz-benchmark/releases/tag/v1.5.0.

### Added
- **Zenodo concept DOI** `10.5281/zenodo.19686928` minted on the
  first public release. `CITATION.cff` `doi:` + `identifiers:`
  populated. README DOI badge (Zenodo) added alongside CI,
  license, Python badges. "Cite this repository" button now
  renders BibTeX + APA on the GitHub landing page.
- **`CITATION.cff`** (new file) — machine-readable citation metadata
  at the repo root. GitHub auto-renders the "Cite this repository"
  button with BibTeX + APA output from this file. Zenodo concept-DOI
  field left as a placeholder comment; populated post first release
  ingest (`10.5281/zenodo.XXXXXXX`). Validates against cff-version
  1.2.0 schema.

### Changed
- **Paper content refresh (LaTeX + HTML + rebuilt PDF).** Four
  targeted additions bringing the paper up to the 2026-04-22 data
  state ahead of the Zenodo public-flip DOI snapshot:
  - Abstract + §1 seed-count bump "more than 4,000" → "more than
    4,500" (manifest at 4,541 with the variance-fill and convergence
    extensions landed).
  - §Limitations 1000-tour convergence extension paragraph. n=90
    β=30 20-seed run at t=1000 shows SD-BKZ has not plateaued: mean
    advantage grows from +1.331 at t=500 to +1.581 at t=1000 (win
    rate 20/20 at both horizons), meaning the paper's 70-tour and
    500-tour numbers understate the asymptotic advantage at
    favourable dimensions by ~1.7×.
  - §Reproducibility fresh-VM install-surface paragraph + variance-
    check paragraph. 100-seed bit-identity confirmed on a cold-clone
    fresh-Ubuntu install. Four groups (n=100 β=30, n=100 β=40,
    n=110 β=40, n=130 β=40) reported at 122 seeds instead of 100 —
    qualitative picture unchanged.
  - §8.2 q=3329 seed 101 post-sample probe sentence. +0.834 nats
    clean classification, outside the 1-100 sampled range, lands
    inside the clean-subset distribution tail.
  - HTML abstract: dropped "(code available upon publication)"
    dangler — code IS available at the GitHub URL, and repo-link is
    already in §Reproducibility.
  - PDF regenerated (31 pages, was 30).

### Changed
- **README paper framing.** Kept `## Paper and patches` heading —
  the repo ships a paper, prepublished via the Zenodo DOI that the
  public flip mints. Dropped the IACR ePrint badge (will be
  replaced by a Zenodo DOI badge at flip time). Added a one-line
  preamble under the section heading clarifying `paper/` is
  generated from `paper/latex/` via `make`. Table row for
  `.tex` source dropped "iacrj LaTeX port (ePrint submission
  format, canonical source)" → "LaTeX source (canonical)" since
  submission is to Zenodo not ePrint.

### Added
- **`.dockerignore`** (new file) — trims the Docker build context by
  excluding raw seed data (`results/seeds/`, `results/cloud/`,
  `results/raw/`, campaign symlink dirs, sensitivity trees, etc.),
  rendered paper artifacts (`paper/*.pdf/html/png`,
  `analysis/figures/*.png`), runtime caches (`logs/`, `_archives/`,
  `.git/`, `__pycache__`, `.ruff_cache`, `.pytest_cache`), and
  local-only files (`.claude/`, `CLAUDE.md`, `*.original.md`).
  Fresh-VM reproducibility test (2026-04-20) observed 557.7 MB build
  context — shrinks to <50 MB. No image content change (all four
  Dockerfiles still `COPY scripts/` only).
- **README `Troubleshooting` subsection** under 90-second quickstart
  covering the three friction points surfaced by the fresh-Ubuntu
  cold-clone test: `docker: permission denied` (missing docker
  group), `pytest: collected 0 items` (wrong `$(pwd)` from a subdir),
  and "run pytest / paper_figures.py inside the image, not host-side".

### Changed
- **Single source of truth for run logs — `logs/pipeline.jsonl`.**
  Removed the dual-write `FileHandler` path in `scripts/sweep_parallel.py`
  (`results/progress.log`) and the `results/health.log` emit path
  (via `.gitignore` entry drop; `health_check.sh` dormant since
  2026-04-07 so writes are inactive). Pipeline.jsonl via
  `scripts/log.py` is now the only authoritative machine-readable
  event stream; human-readable output stays on stdout. Per-script CI
  lint (`scripts/lint_logging.py`) already prevents new violations.
  (commits 8f6aa5e, 91de44a)

### Removed
- **Legacy `.log`/`.pid`/`.out` debris from `logs/` + tracked
  `results/progress.log` (173K) + untracked `results/health.log`
  (24K).** All 19 files archived to
  `_archives/logs_legacy_2026-04-20.tar.gz` with SHA-256 in
  `_archives/CHECKSUMS.sha256` before rm. `logs/` retains
  `pipeline.jsonl` + `.gitkeep` + active stdout captures only.
- **Empty dir `results/3x_tours_extended/`** — scaffold never
  populated, rmdir.
- **Byte-identical duplicate `results/paper_claims/profile_decomposition.json`**
  (paper-cited canonical is `results/profile_decomposition.json`).
  Archived dup at `_archives/profile_decomposition_paper_claims_dup_2026-04-20.tar.gz`.

### Fixed
- **`.gitignore`** now tracks `.ruff_cache/` + `.pytest_cache/`
  explicitly (were untracked by accident); dropped stale
  `results/health.log` entry post-rm.
- **`tests/test_math_core_edge_cases.py:98`** — removed dead
  `peak_idx` local (ruff F841); assertion logic unchanged.
- **GHA Node.js 20 deprecation warning silenced** via
  `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: 'true'` env on
  `.github/workflows/build-and-verify.yml`. Low-risk quick patch
  ahead of the 2026-06-02 "forced Node 24 by default" cutover and
  2026-09-16 Node 20 removal. Canonical action-version bumps
  (checkout@v4→v5, etc.) deferred until availability verified
  to avoid mid-sweep CI breakage.

### In progress
- **Reader-facing documentation pass (`v1.4-docs` branch).** README
  rewrite, SECURITY.md + `docs/disclosure/fplll_gso_kahan_findings.md`,
  CONTRIBUTING.md, ROADMAP.md, `docs/design_decisions.md` (2 ADRs),
  Makefile, `docs/pipeline_log_queries.md`, `docs/incident_q3329_post_mortem.md`,
  `docs/seed_manifest_schema.md`, CHANGELOG in-repo. All ADDITIVE —
  zero changes to paper, seeds, scripts, Docker, or CI gates. Hard
  invariant: SHA-256 of every paper-cited file preserved (14/14
  figures byte-identical vs v1.3.1 baseline). Targets `v1.4.0`
  post-v1.3.1.

### Deferred
- **Campaign config file (`config/sweep.toml`)** — parked, not
  scheduled. Replaces hardcoded `BETAS` / `NS` / `TOURS_BY_BETA`
  constants across sweep scripts with a single TOML-defined
  campaign registry. Revisit trigger: ≥2 new runners per month,
  cross-script constant drift, or a future seed-index rev that
  wants per-campaign provenance in seed JSONs. Today the hardcoded-
  constants-per-script pattern is stable and self-documenting; the
  migration cost is not justified.
- **Legacy-path symlink drop (v2.0.0).** Post-v1.3 the canonical
  seed tree is `results/seeds/<campaign>/...` but backwards-compat
  symlinks at pre-v1.3 paths (`results/raw/`, `results/cloud/`,
  `results/q3329/`, ...) are preserved for one release cycle so
  paper-era SHA-256 receipts keep resolving. v2.0.0 drops those
  symlinks with coordinated paper §9 + CI + analysis argparse edits;
  `results/seed_path_crosswalk.csv` becomes the permanent old→new
  reconciler.

## [1.3.1] — 2026-04-19

Tag: `v1.3.1`. One-night coverage-expansion branch (originally
`overnight-sweep-20260418`, renamed `v1.3-coverage-expansion` pre-merge)
adds 25 q=3329 seeds at the paper-headline 1000-bit precision and
fixes a forward-compat gap in the v1.3 manifest walker that the sweep
surfaced.

### Added
- **+25 q=3329 seeds at 1000-bit MPFR** across intermediate dimensions:
  - n=70 β=30 seeds 21–25 (+5 seeds, 3.09 h wall on 22-worker pool)
  - n=80 β=30 seeds 21–30 (+10 seeds, 6.93 h wall on 8-worker pool)
  - n=90 β=30 seeds 21–30 (+10 seeds, 8.72 h wall on 8-worker pool)

  Completes the intermediate-dimension 30-seed fill (previously
  20 seeds per group at 250-bit MPFR) at paper-§8 precision.
  Per-seed advantages range +0.17 to +0.98 nats, all positive;
  consistent with paper §8 clean-subset mean +0.524 at n=100.
  14 `WARNING: 1 get_r values <= 0` entries from the n=90 pool
  (logged to `results/clamp_events.jsonl`) — expected per the
  paper §8 GSO-instability family, no impact on advantage values.
  (c53e08a)
- **`scripts/run_overnight_q3329_intermediate_1000bit.py`** — one-shot
  overnight fill runner. Writes through `_seed_paths.seed_path_for`
  so new seeds land natively at
  `results/seeds/q3329/p1000_mt70/n{n:03d}_beta{b:02d}/seed{s:04d}.json`.
  Restart-safe (file-exists probe against the v1.3 layout).
  (6005490)
- **8 test cases in `tests/test_build_seed_manifest.py`** covering the
  new v1.3-native walker path: direct-in-tree parse, symlink/canonical
  dedup, per-campaign path extraction (main / q3329 / cliff500 /
  fplll_sensitivity / tours3x / convergence), cloud & fat suffix
  handling, unknown-campaign rejection. (2b5365c)

### Fixed
- **`scripts/build_seed_manifest.py` walker forward-compat gap.** The
  v1 walker (commit 84564ab, shipped in v1.3.0) enumerated only the
  pre-v1.3 `CAMPAIGN_DIRS` set (raw, cloud, q3329, q3329_n*_beta30,
  q3329_degenerate, cliff_500bit, fplll5{43,44,5}_sensitivity,
  3x_tours, 3x_tours_extended, convergence, convergence_test),
  followed symlinks at those old paths, and recorded canonical
  `results/seeds/` destinations via `os.path.realpath`. Worked for
  pre-migration files because `migrate_seeds_to_new_layout.py`
  (ac52379) left backwards-compat symlinks at every old path.

  Gap: new seeds written directly to the v1.3 tree via
  `_seed_paths.seed_path_for()` — for example this release's
  overnight fill — bypass the walker entirely. No legacy symlink =
  no walker visit = no manifest entry = `lint_seed_manifest.py`
  flags an orphan.

  Fix: add a v1.3 native walker that recurses `results/seeds/`
  and parses `(campaign, n, β, seed, q, precision, max_tours,
  fplll_version, is_cloud, is_fat)` from the leaf-dir + filename
  pattern. Parser mirrors the emit logic in `scripts/_seed_paths.py`
  — any drift there must be mirrored here. After both walkers run,
  entries dedup by canonical `os.path.realpath()` so a file
  reachable via both a legacy symlink and its new canonical path
  lands once. (2b5365c)

### Changed
- Manifest entry count: **4387 → 4412** (+25 q=3329 intermediate-fill
  seeds). Per-campaign totals:
  | campaign            | entries | delta |
  |---------------------|---------|-------|
  | cliff500            |    20   |   0   |
  | convergence         |    40   |   0   |
  | fplll_sensitivity   |    15   |   0   |
  | main                | 3,505   |   0   |
  | q3329               |   332   | **+25** |
  | tours3x             |   500   |   0   |

  `lint_seed_manifest --sha-check`: 0 orphan / 0 ghost / 0 drift on
  the v1.3.1 tree.

## [1.2.0] — 2026-04-18

Tag: `v1.2.0` at commit `c66160e` (merge of `v1.2-consolidation` into
main). Landed via a 17-commit feature branch spanning Phases 1–5 of the
code consolidation, a confirmation suite, ruff CI, and a final polish
pass. Paper numerics unchanged — every hot path verified bit-identical
to v1.1.0 via `scripts/confirm_v1_2.py` (30 seeds × 4 `run_single`
paths) and `scripts/test_math_core_parity.py` (576 comparisons, 0
failures).

### Added
- **`scripts/_math_core.py`** — single authoritative source for
  `ln_fixed_point`, `build_lwe_kannan`, `metrics_from_gso`, `log_clamp`,
  and `_safe_log_r`. Full type hints; magic numbers (`CLAMP_FLOOR_R =
  1e-300`) lifted to named constants. Replaces 6 inlined copies across
  `sweep_parallel`, `sweep_cloud`, `q3329_verify`,
  `overnight_experiments`, `run_3x_extended`, `run_convergence_test`
  (9413d81, b672a31).
- **`scripts/_bkz_core.py`** — shared `run_single(n, beta, seed)`
  implementation lifted out of `sweep_parallel`, `sweep_cloud`, and
  `q3329_verify`. Named constants (`STAGNATION_THRESHOLD`,
  `HEARTBEAT_EVERY`, `CLAMP_FLOOR_R`). Heartbeat-logged via
  `PIPELINE.info` every 25 tours (152bafc, a4b3e61).
- **`scripts/_signal_utils.py`** — shared `managed_pool`
  context-manager factoring out the 4-way-duplicated `SIGINT` handler +
  `Pool.terminate()` pickle-failure-survival logic (076a264, 8a82053).
- **`scripts/confirm_v1_2.py`** — end-to-end confirmation harness that
  regenerates 30 reference seeds across 7 `(n, β)` groups and 4
  `run_single` paths (`sweep_parallel` / `sweep_cloud` / `q3329_verify`
  / `overnight_experiments`) and asserts byte-identity against the
  v1.1.0 baseline JSONs (6284e00).
- **`scripts/confirm_extra_compare.py`** — complementary cross-path
  byte-compare helper for seeds not covered by `verify.sh` reference
  set (bf70300).
- **`scripts/test_math_core_parity.py`** — standalone 576-comparison
  parity check: 60 `ln_fixed_point` pairs × 6 legacy copies + 36
  `build_lwe_kannan` pairs × 6 legacy copies. Runs in ~0.2 s, 0
  failures on the v1.2.0 tree.
- **`scripts/test_log_clamp_wrappers.py`** — smoke tests for the
  `log_clamp` thin-wrapper pattern introduced in Phase 4a.
- **`tests/test_math_core_edge_cases.py`** — pytest suite covering
  clamp semantics, `log_clamp` schema, `ln_fixed_point` boundaries,
  `build_lwe_kannan` determinism, `metrics_from_gso` sensitivity to
  negative `get_r` values. 17 tests, ~0.2 s, wired into CI (076a264).
- **`scripts/find_bugs_via_tags.py`** — static bug-hunt over the
  `.tags` ctags index: duplicate function definitions, defined-
  but-unreferenced symbols, private (`_foo`) leaks across files
  (19cb533).
- **ruff style + dead-import drift guard** in CI: `[tool.ruff]` in
  `pyproject.toml` (line-length=100, F/W codes + I001, scripts/ +
  analysis/ scope). New `build-and-verify.yml` step fails on any drift
  (a4b3e61, 1c96e71).
- **`scripts/lint_logging.py`** + CI step enforcing the centralised-
  logging policy: every entry-point script under `scripts/` and
  `analysis/` must import `scripts/log.py:get_logger` so events flow
  to `logs/pipeline.jsonl` (3a12c77, bf70300).

### Changed
- `sweep_parallel.py`, `sweep_cloud.py`, `q3329_verify.py`,
  `overnight_experiments.py`, `run_3x_extended.py`,
  `run_convergence_test.py` — all six now import `ln_fixed_point`,
  `build_lwe_kannan`, `metrics_from_gso`, and `log_clamp` from
  `_math_core` instead of maintaining private copies
  (a37bdfb, 0f33306, 70e2edf, 95dc826).
- `sweep_parallel.py`, `sweep_cloud.py`, `q3329_verify.py` — now
  import `run_single` from `_bkz_core` instead of maintaining private
  copies. Net diff: −914 lines, +2212 lines (of which ~1800 are new
  tests / confirmation harnesses, not production code) (152bafc,
  d3999d2).
- Pipeline logging production-grade upgrades: structured
  `PIPELINE.info` events across `sweep_parallel`, `sweep_cloud`,
  `confirm_v1_2`, `run_cliff_500bit`; `analysis/` scripts routed
  through `get_logger` (3a12c77).
- `scripts/overnight_experiments.py` and `scripts/run_3x_extended.py`
  now import `run_single` from `_bkz_core` where the thin-wrapper
  swap is bit-safe (d3999d2).

### Fixed
- `managed_pool` context-exit path: use `Pool.terminate()` (not
  `.close() + .join()`) on context-manager exit so the pool survives
  a pickle failure in a child worker. Previously, a pickle error hung
  the parent indefinitely (8a82053).
- `q3329_verify.py`: `store_per_tour` flag position moved to match
  Phase 2 signature; prior order caused an unchecked positional
  argument mismatch on the q=3329 path (d3999d2).
- Ruff clean pass: F541/W293 auto-fix + 5 F841 dead-local removal
  across `scripts/` and `analysis/`. Parity-verified bit-identical
  via `test_math_core_parity` (576 comparisons, 0 failures) +
  `verify.sh` + pytest 17/17. Stylistic-only, zero numerical impact;
  precondition for the ruff CI gate (added in a4b3e61) to actually
  pass on merge to main (1c96e71).

### Removed
- `dashboard/` directory — unused since v1.0; git history preserves
  the last working version. Saves 150+ MB of static assets from
  `git clone` (896e25c).

## [1.1.0] — 2026-04-18

Tag: `v1.1.0` at commit `896e25c`. LaTeX port of the paper, Kahan
fplll patch published, paper v1.1 substantive edits (§3.7, §7.4),
cliff 500-bit precision test, fplll 5.4.x version-sensitivity test.
Paper numerics unchanged from v1.0; 250-bit MPFR remains the
authoritative precision for all sweep seeds.

### Added
- **iacrj LaTeX port of the paper** — `paper/latex/sdbkz_paper_latex.tex`
  (30 pages, IACR journal class, CC-BY-4.0, cryptobib citations).
  Mirrors the content-locked v1.0 HTML verbatim; numbers audited clean
  against `paper_audit_handoff/` snapshots; all 12 figures renamed to
  paper order (`fig01.png`–`fig12.png`), preemptively fixing the
  scrambled-filename issue (Finding 18) on the LaTeX side. Vendored
  `iacrj.cls` + `metacapture.sty` + `abbrev3.bib` — no submodules
  required. `paper/latex/Makefile` provides a one-command rebuild
  (7127712, 6be7589).
- **`patches/fplll_gso_kahan.patch`** + README — ships the Kahan-
  compensated fplll GSO patch referenced in paper §8.3. Closes the
  gap between the paper claim and the public repo so readers can
  reproduce §8.3 directly. Verified against fplll HEAD (`1987472`,
  2025-10-15): clean `git apply`, full build, **15/15 `make check`
  pass**, matching the 2026-04-10 Docker build on fplll 5.5.0. Only
  needed for q=3329 reproduction; q=97 unaffected. (d57808c + 161f188)
- `.gitattributes` with `paper/** linguist-documentation` so GitHub
  language stats reflect actual benchmark code (Python, Shell,
  Dockerfile) rather than the 10k-line vendored `abbrev3.bib`
  (086f6a2).
- "Paper and patches" section in the README pointing readers at
  `paper/`, `paper/latex/`, and `patches/`.
- **β=40 cliff precision-robustness test** — 20 seeds at
  $n=130$, $\beta=40$, $q=97$, 500-bit MPFR (double the 250-bit
  main-sweep precision). Confirms the cliff is structural, not a
  squared-form GSO recurrence artifact: mean advantage shifts only
  $-1.370 \to -1.282$ nats ($\Delta=+0.088$, 6.4% softening), win rate
  unchanged at 0/20, Cohen's $d$ vs zero strengthens to $-11.4$
  (baseline $-9.70$) due to tighter variance at higher precision.
  Reviewer-defensive coverage of paper §6.3. Runner:
  `scripts/run_cliff_500bit.py` (856f436); fat seeds:
  `results/cliff_500bit/` (636186a); evidence:
  `results/paper_claims/cliff_precision_robustness.json`. 8.85 h on
  22 workers single-wave.
- **fplll 5.4.x vs 5.5.0 version-sensitivity test** — 15 seeds (5
  per legacy version) at the canonical $(n=100, \beta=30, q=97,
  250\text{-bit MPFR})$ sweep point under fplll 5.4.3 / 5.4.4 / 5.4.5
  (each source-built against fpylll 0.6.0 inside a custom Docker
  image), compared to the $5.5.0$ baseline shipped in fpylll 0.6.4.
  **Every seed bit-identical to the 5.5.0 baseline to 18 decimal
  digits** despite three SONAME bumps across the tested window
  (libfplll.so.7.1.0 → 8.0.0 → 8.0.1 → 9.0.0). Welch t = 0.0 vs
  baseline for all three legacy versions. Indicates that 250-bit
  MPFR dominates whatever fplll-internal numerical drift exists
  between these tags. Reviewer-defensive coverage of the fplll
  pin in §3.7 Reproducibility. Infrastructure: `Dockerfile.fplll54`,
  parameterised `Dockerfile.fplll_legacy`, `scripts/run_fplll54_sensitivity.py`,
  `analysis/fplll_sensitivity_compare.py`; evidence:
  `results/paper_claims/fplll_version_robustness.json`; fat seeds:
  `results/fplll5{43,44,5}_sensitivity/`. 8.85 h on 22 workers
  single-wave (15 in flight, 5 queue). Build matrix + tags blocked
  by API/Python compat documented in the Dockerfile header.
  (bc9eaf8)
- **`scripts/_runner_core.py`** — shared `run_pool()` skeleton
  factoring out the ~80-line argparse / Pool.imap_unordered /
  per-seed status / PIPELINE.info boilerplate from the five existing
  `run_*.py` wrappers. Paper-numerical-neutral shell code; safe to
  land without verify.sh. New wrappers should import directly;
  existing wrappers keep their inlined versions until the v1.2
  consolidation Phase 2 swap. (13e8a53)

### Changed
- `paper/sdbkz_paper.html` + `paper/sdbkz_paper.pdf`: Acknowledgements
  now render "Dylan Chambers Bourgeois" (no hyphen). §9 Reproducibility
  appended one sentence pointing readers at
  `patches/fplll_gso_kahan.patch` (7f8f690). Same edits mirrored into
  the LaTeX port.
- `paper/latex/main.tex` → `paper/latex/sdbkz_paper_latex.tex` and
  `main.pdf` → `sdbkz_paper_latex.pdf` so every rebuild produces an
  unambiguously-named file (6be7589).
- **Paper v1.1 substantive edits** (LaTeX only; HTML already
  mirrored):
  - Fixed p-value underflow artifacts in Table 4, §4 "Statistical
    rigour", and §10 Conclusion: `<10^{-50}`, `<10^{-20}`, `<10^{-18}`
    all collapsed to `<10^{-15}` (SciPy double-precision floor; 29
    replacements).
  - §4 RHF/$d(\mathrm{LN})$ decoupling sharpened with a per-seed
    verification on the $n=100$, $\beta=30$ sample (30 seeds): $r =
    -0.14$ ($p=0.48$) Pearson correlation between per-seed RHF and
    $d(\mathrm{LN})$ advantages — metrics measure orthogonal basis
    properties.
  - §8.2 extended to $n=110$: instability persists (≥22 degenerate
    seeds in partial run, both algorithms affected every seed);
    SD-BKZ reaches the degenerate state earlier on average (median
    first-spike tour 4 vs 6–11).
  - **§7.4 Limitations** gained a precision-robustness one-liner
    for the $\beta=40$ cliff at $n=130$: 500-bit MPFR re-run (20
    seeds) moves the mean advantage by only $+0.088$ nats and keeps
    win rate at 0/20, confirming the cliff is structural rather than
    numerical. Backported to the HTML mirror; LaTeX PDF rebuilt
    (06c6e04).
  - **§3.7 Reproducibility** gained an fplll version-robustness
    one-liner: the canonical $(n=100, \beta=30)$ sweep point produces
    bit-identical advantages to 18 decimal digits across fplll
    5.4.3 / 5.4.4 / 5.4.5 / 5.5.0 (all 15 seeds, 4 SONAMEs). Confirms
    the paper does not depend on the specific fplll point version
    inside the wheel. Mirrored to HTML; LaTeX PDF rebuilt 30 → 31
    pages (single sentence pushed overflow). (54ec605)

### Fixed
- Replaced malformed `patches/fplll_gso_kahan.patch` with a
  regenerated single-hunk version. The file initially shipped in
  d57808c was a byte-for-byte copy of the broken original from the
  2026-04-10 investigation directory — `BUILD_REPORT.md` flagged it
  as having a corrupt first hunk (header claimed 6→7 lines but body
  contained 6→6). The actual patch used for the 55-seed verification
  was a corrected version written inside an ephemeral Docker
  container and never saved back. Caught during pre-submission
  apply-check against fplll HEAD. (161f188)

## [1.0] — 2026-04-14

Initial public release of the benchmark and v1.0 paper. Tag: `v1.0`
at commit `40991a4`.

### Added
- `scripts/run_sweep_fill.py` — general-purpose β=40 gap-filler,
  replaces per-group one-off scripts. Auto-detects physical core count,
  checks both `raw/` and `cloud/` for existing seeds, `--dry-run`
  support (4239963)
- `scripts/run_q3329_n100_local.py --start/--end/--workers` flags for
  splitting q=3329 expansion across machines (1a58930)
- n=120 β=40 complete at 100 seeds (75 cloud + 25 local, 4239963)
- n=130 β=40 seeds 76-99 (24 of 25, run in progress)

### Changed
- Documentation structure split: `CHANGELOG.txt` → `CHANGELOG.md` +
  `incidents.md` + `sessions/`. Legacy log frozen as
  `CHANGELOG.txt.frozen-2026-04-09`.

### Fixed
- `scripts/sync_research.sh` now backs up `results/convergence/` and
  `results/convergence_test/` to the Research mirror (f3a75f5,
  see legacy Incident 23)
- **Incident #29:** `run_sweep_fill.py` was created and referenced in
  Dylan's handoff doc but never pushed. Dylan lost one overnight compute
  window (~18h delay on 25 seeds). See `incidents.md` #29.

## Pre-split history

Everything before 2026-04-09 lives in `CHANGELOG.txt.frozen-2026-04-09`.
That file is the authoritative record for the campaign's first phase
(repo creation through n=140 β=30 convergence test). Do not edit it.
