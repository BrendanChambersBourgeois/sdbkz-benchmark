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
- JOSS submission draft: `paper.md` + `paper.bib` at repo root (software-artifact paper; findings stay on Zenodo), `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1). Compiles with `openjournals/inara`; `/paper.pdf` gitignored. Submission gated until 2026-10-23 (JOSS six-month public-history requirement).
- **+2,330 seeds** from the two-node β=40/β=50 campaigns, all `status=completed`: `ntru` +1,988 (β=40 fill, n=109–179, q=503–7177 — canonical manifest 11,561 → 13,549), `ntru_b2` +240 (80 each at n=167/173/179), `ntru_b2_probe` +3, `ntru_g6k` +99 (G6K manifest 2,384 → 2,483). The G6K batch carries the β=50 frontier cells: n=181 q=4591 4/9 integer-exact (seed0002 absent — g6k sieve assertion abort, INC-61), q=3733 1/20 (SD-only, at 2.30× q_fat where β=40 is 0/20), q=4871 12/20 (BKZ 5, SD 8, one both-leg), and the n=179 q=4591 cell completed to 10/10 under the 86,400 s seed cap (SD 5, BKZ 3). Both manifests rebuilt; `lint-manifest` and `lint_g6k_manifest` report 0 violations.
- **`results/seeds/ntru_flatter/` A/B probe tree** (124 seeds, ran 2026-08-13): paired `baseline`/`flatter` cells at n=130/140/150 (20+20 each) plus a partial n=157 cell (2+2), testing [flatter](https://github.com/keeganryan/flatter) as a pre-reduction step ahead of the standard BKZ/SD-BKZ run. The flatter step ran outside the committed campaign tooling, so the tree is registered in `lint_seed_manifest.py` as a deliberate non-manifest tree until a driver lands; treat it as exploratory, not paper-grade.
- **`[campaigns.ntru_b2_probe]`** — per-tour re-run of `ntru_b2` seeds showing the mid-trajectory dLN discontinuity, into its own seed tree so no `ntru_b2` seed is re-opened. Ran 2026-08-25: 3 seeds at n=179 q=4591 β=40, now at `results/seeds/ntru_b2_probe/q4591/p500_mt50/n179_beta40/`. **The `store_per_tour = true` capture did not take effect** — the flag is a silent no-op on the `run_campaign.py` path (INC-59; recorded, not fixed), so the seeds carry no per-tour Rankin/GS/RHF arrays and are field-identical to their `results/seeds/ntru/` twins apart from timing fields. Reader caveat for this tree and for the `ntru_b2` n=167/173/179 β=40 cells generally — `advantage` is the difference of the two legs' final `d(LN)`, and only some legs take the collapse step within `max_tours`, so a per-cell mean over `advantage` mixes stepped and unstepped legs and is an artifact; the runner's printed `mean advantage=` line for these cells is not a quotable number. Investigation note: `Research/postmortems/dln_discontinuity_2026-08-25_investigation.md`.
- **g6k as a second reduction engine** behind a backend seam. `scripts/_engine_backends.py` (`make_backend` → `fplll`|`g6k`); `_bkz_core.run_single` gains a `backend` kwarg; the tour loop is engine-blind (ADR-006).
- **g6k self-dual BKZ** (`sdbkz` variant): primal + dual-mode pump-n-jump per tour, validated against fplll `SD_VARIANT` (ADR-008).
- **`Dockerfile.fplll_patched`** — fplll 5.5.0 + Kahan §8 patch + fpylll 0.6.4, `make check` 15/15; `[campaigns.ntru_n127_patched]` rerun (§8 validation #2).
- **`scripts/compare_xengine.py`** — cross-engine (fplll vs g6k) per-seed comparator → `results/validation/`.
- **`results/validation/`** tree (ADR-007/008 determinism + cross-engine records, README, schema). Separate from the science seed trees; never enters `seed_manifest`.
- Campaign config gains `backend` and `seed_tag` fields; `g6k_probe.py` gains `--tours`/`--reseed`; new campaigns `ntru_g6k_pilot`, `ntru_g6k_rhf`, `ntru_xeng_n89`, `ntru_xeng_tail`.
- **NTRU β=20 ball-out**: 1,858 seeds across 57 cells (n=67–113 precision ladders), completing the DSD-onset trend end to end — including the n=113 endpoint. Manifest 4,741 → 8,741. (The never-idle `forever_runner` NTRU fill has since continued; the manifest now stands at 11,561 fplll entries + 2,384 g6k entries — the `ntru` campaign, 6,740 seeds, is now the largest.)
- **`scripts/extract_dsd_onset.py`** — reference-free DSD-onset extractor (two-part criterion, 50%-rate crossing, per-n threshold); reproduces paper-2 Table 2 from the seed tree.
- **`scripts/build_g6k_manifest.py`** — populates `g6k_seed_manifest.json` seeds[] from the on-disk G6K tree (verify-gated, threads=1 contract). 0 → 464 entries; the G6K campaign seeds now have full SHA-256 gate coverage (previously only the reference probe).
- **Per-seed central logging**: both runners emit seed done/failed events to `logs/pipeline.jsonl`; seed JSONs untouched (byte-identity preserved).
- **Steam Machine second compute node.** (A Valve Steam Machine running SteamOS; the node keeps the name `steamdeck` in configs, logs, and `ctx.node` for continuity.) `forever_runner.py` gained node-profile flags; the node runs a podman-wrapped gated unit off its own worklist file, and `make node-push-worklist` / `make node-status` / `make node-pull` drive it from the workstation (pulls never overwrite an existing seed and merge the node's `pipeline.jsonl` by timestamp). New `[campaigns.ntru_g6k_backfill]` gives the node a never-idle floor: g6k β40 twins of the workstation's `ntru_b2` frontier cells, written into the `ntru_g6k` tree, building the cross-engine β40 corpus out of idle time. Cell ownership is split so the two nodes never generate the same seed path. `node_sync._merge_log` is now content-keyed, so a pull no longer re-appends the node's campaign records on every run. (`501d0a5b`)

### Changed
- **Ops hardening after INC-58/INC-60**: `forever_runner` warns (`event=fast_done`) when a worklist line returns rc=0 in under 300 s — a full-cell re-dispatch and a silent no-op look identical from outside — and its filler log line now names the actual filler tree (it hardcoded `ntru_b2`, wrong on the deck's `ntru_g6k` filler); `node_sync` status classifies *why* a node did not report (auth-blocked → open the ControlMaster socket first, vs host down, vs ssh timeout) instead of one `reachable=False` for all cases; the steamdeck unit replaces its `StartLimitIntervalSec=1800`/`StartLimitBurst=5` budget — which a deterministic 221 ms failure exhausted in seconds, stranding the node for 36 h — with `StartLimitIntervalSec=0` + `RestartSec=300`.
- **`results/wall_cap_events.jsonl` is now gitignored and mirrored instead of committed**, matching the `results/clamp_events.jsonl` precedent. It is the INC-56 wall-cap side log — one record per seed killed at the `--seed-timeout-s` cap — and it appends without bound across wall tests, so keeping it in git history would churn the repo on every campaign run. Preserved on disk and copied to `Research/data/analysis/` by a paired `cp` line in `ops/sync_research.sh`; that script lives outside this repository, so the pairing is an edit plus a commit rather than a single commit.
- **Renamed the `paper/` directory to `paper1/`** for symmetry with `paper2/` (the NTRU cross-engine technical report). Updated the build target, figure-parity gate (`sync_paper_figures.py`, the CI step), `.dockerignore`/`.gitattributes`, the top-level-dir allowlist, and the current-facing docs (README, SECURITY, CONTRIBUTING). Historical CHANGELOG/audit/disclosure entries keep their original `paper/` paths as point-in-time records.
- **Folded 3 duplicate engine loops onto a shared `_bkz_core.dln_trajectory`** (`run_3x_extended`, `run_convergence_test`, `overnight_experiments`) — removes the run_single-divergence hazard (ADR-001 class); per-seed JSON byte-identical.
- CI `g6k-verify` flipped to a hard byte-identity gate (reference captured).
- **DSD criterion finalised as the n-dependent two-part test** (collapse count ≤ n+1 at threshold log√(2n·2/3)+0.5 AND min log-norm > 1.5). The b1-only variant over-fires on sub-fatigue bases and is rejected; the frozen n=89 constant (2.888) is retained only as a documented sensitivity alternate. Paper-2 Table 2 regenerated under the canonical criterion (gap trend ≈0% → 28%, threshold-robust).
- Paper-2 accuracy pass following an internal audit: §6 cross-engine soundness containment corrected (the record shows one sieve-only firing); §2.3 now defines the two-part criterion (was the rejected b1-only form); §7 clamp statistics restated from the event log (157 of 208 in the quoted range, 40 deeper); statistics relabelled (standard deviation vs variance; linear vs log-norm ratios); bibliography corrected (missing first author, wrong report title, citation-record title mismatch).

### Fixed
- **`_pidlock` reclaim TOCTOU**: two racers over a stale lock could both acquire — a reclaimer that had passed the liveness check could unlink the fresh lock a faster reclaimer just created. Reclaim now runs under an exclusive flock on a `<lock>.guard` sidecar and only unlinks a lock file that still exists and is stale; creators stay guard-free. Caught by CI on `23767265` (`test_race_stale_lock_exactly_one_reclaimer`, 2-winner assert).
- **g6k campaigns dispatched where the g6k module is missing silently no-opped (INC-60).** All 12 queued β=50 worklist lines died host-side in ~66 s each (`ModuleNotFoundError: No module named 'g6k'`, 0/20 written) yet returned rc=0, so `forever_runner` archived the whole 7.2-day ladder as done in ~12 minutes. Two-part fix in `run_campaign.py`: (1) a g6k-backend campaign re-execs itself inside `sdbkz-g6k:dim384` when the module is not importable (docker `--user` so seeds stay user-owned, `nice -n 19` because containerd children never inherit the runner's `Nice=19` drop-in, recursion-guard env; broken image / missing docker fail loud with rc=2); (2) a run in which every *attempted* seed failed now exits 1 — all-skip and partial failure remain rc=0 — so the runner's FAILED_LOG and consecutive-failure stop-loud counter engage instead of archiving a silent no-op.
- **Leg attribution on failure records was inference (INC-56/57/58-era note, closed).** `_bkz_core.run_single` gained an optional `leg_cb` called as each variant starts (side-channel only; golden tests byte-identical). `seed failed` pipeline events and `results/wall_cap_events.jsonl` kill/crash records now carry `variant`, and every wall_cap_events record carries `ts`. Crash-record breadcrumbs are best-effort (the mp.Queue feeder thread may not flush before a native death).
- **Steam Machine node could not write its bind-mount** — the rootless-podman unit needs `--userns=keep-id`; without it the container user maps to a subuid and every write under `/experiment` fails. The node was dead 36 h before this was found (INC-58).
- **Single-instance lock shared by `forever_runner` and `onset_driver`** (`scripts/_pidlock.py`, ultrareview PR #3). Each driver had half the lock: `forever_runner` created atomically but matched any argv basename, so a SIGKILL-orphaned lock whose pid was recycled to `tail -f scripts/forever_runner.py` blocked the restart — and `main()` exited 0, which `Restart=on-failure` read as an intended stop (never-idle floor silently dead); its `.decode("replace")` also raised an uncaught `LookupError` on every live-pid collision. `onset_driver` had the anchored match but a non-atomic `exists()`→`write_text()` (two racers could both hold the lock; 10–12 of 12 racers "won" in the new test, 1 after). Lock refusal now exits 3 so a false block is visible in `systemctl status`.
- **Capped scheduler (`_run_tasks_capped`, INC-56 path) no longer loses native crashes.** A seed worker dying on SIGSEGV/SIGABRT in fplll/MPFR/g6k — or an external SIGKILL — bypassed the `BaseException` guard, enqueued nothing, and was `del`'d from the tally with no log line (wave ended `done < total`, silently). Now a `crashed` bucket, a `worker_crash` event in `results/wall_cap_events.jsonl` (exitcode + signal name), a `PIPELINE.error`, and the invariant `results + killed + crashed == tasks`. `wall_cap_kill` records are byte-identical to before.
- **INC-55 — g6k CI SIGILL (exit 132), fixed.** The g6k siever `import` `SIGILL`ed on the v2-only GitHub runners the fleet drifted to include. Root cause: g6k's `./configure` defaults to `--enable-native`, which appended AVX2/FMA on top of the `Dockerfile.g6k` `-march=x86-64-v2` CFLAGS/CXXFLAGS — so the earlier "v2 pin" was a no-op (disassembly of the shipped `.so` showed AVX2 `ymm`/`vfmadd`) and the binary kept faulting on v2-only runners. Fix: pass **`--disable-native`** to g6k's configure so the v2 target actually applies. The rebuilt siever is genuinely v2 (0 AVX2/FMA/AVX512 instructions) and runs on every x86-64-v2+ runner. The determinism reference is unchanged (`basis cf22519d…`/`rprof d4faf05a…`) — the n=80/β60/seed42 probe is ISA-invariant (verified: the AVX2 and pure-v2 builds produce identical SHAs), so the gate needed no re-baseline.
- **fplll Kahan patch — corrected sign + split.** The shipped patch had the Kahan compensation sign flipped (inert); corrected to `c = (t − ftmp1) + y`, moved scratch to member vars, and hardened the regression test. The deliverable is now split into a code-only `patches/fplll_gso_kahan.patch` + a separate `patches/fplll_gso_kahan_tests.patch`. Upstream PR #550 was closed unmerged (2026-05-17); the corrected patch is kept local-only (docs across README/SECURITY/ROADMAP/disclosure reconciled to that framing).
- `Dockerfile.fplll_patched` ran as root → bind-mounted seeds were root-owned (INC-40, INC-32 recurrence); added the non-root `runner` USER. Existing root-owned `ntru_patched` seeds chowned back.
- `dln_trajectory` no longer hardcodes the g6k Siever seed (latent determinism trap; fplll path was unaffected).
- `_config` now validates `seed_tag` against known trees; `compare_xengine` guards missing rhf fields.
- `lint_seed_manifest.py` orphan walk no longer flags the deliberately-separate trees (`results/validation/`, `results/seeds/ntru_g6k/`, `results/seeds/ntru_patched/`) — 487 false orphans → 0.
- Top-level-dir test allowlist updated for the `paper/` → `paper1/`+`paper2/` rename (latent failure that would have surfaced at merge).
- `CITATION.cff` cited the v1.5.0 version DOI as the concept DOI; now points at the true concept DOI (10.5281/zenodo.19686927) with the v2.0.0 version DOI as a second identifier. (Fixed on `main`, d951f11.)

## [2.0.0] — 2026-06-03

**Breaking layout change.** The v1.3-era back-compat symlink tree at
`results/{raw,cloud,q3329,q3329_n*_beta*,q3329_degenerate,cliff_500bit,
fplll5*_sensitivity,3x_tours,3x_tours_extended,convergence,
convergence_test}/` has been deleted. The canonical seed layout is now
`results/seeds/<campaign>/...` exclusively. `results/seed_path_crosswalk.csv`
(committed) is the permanent old→new reconciler for any external
citation that references a pre-v2 path.

### Removed
- 4,387 back-compat symlinks across 14 legacy top-level directories.
  All pointed into the v1.3 canonical tree; removing them is a layout
  change only (no per-seed JSON deleted; the underlying data lives
  at `results/seeds/<campaign>/<...>/seedNNNN.json` as before).
- `scripts/lint_seed_manifest.ALLOWLIST_LEGACY_PATHS` legacy entries
  retired; the allowlist now points only at the 10 3x_tours pilot
  seeds (`results/seeds/tours3x/pilot/`) which were physically
  relocated from the deleted `results/3x_tours/` legacy dir.
- Legacy `--seed-dirs` default of `["results/raw", "results/cloud"]`
  on `analysis/gsa_robustness.py` and the matching docstring on
  `analysis/_data.load_all_seeds`.

### Changed
- **`analysis/_data.load_all_seeds`** — pre-v1.3 positional `(raw_dir,
  cloud_dir, ...)` mode is now an off-tree-only escape hatch. The
  canonical call form is `load_all_seeds(campaign="<name>", q=97)`
  against `results/seed_manifest.json`.
- **`scripts/sweep_parallel.scan_completed`** — legacy `results/raw/`
  glob fallback retired. Resumability now walks the v1.3 tree only.
- **`scripts/sweep_cloud.s3_key` + `scripts/submit_jobs.check_completed`** —
  S3 prefixes routed through `_seed_paths.seed_path_for`. Cloud
  campaign is decommissioned (since 2026-04-10); these are dead code
  paths today but will land seeds at the campaign-tree prefix on any
  future restart, matching on-disk layout byte-for-byte.
- **`scripts/confirm_extra_compare.GROUPS`** — archive paths rewritten
  to thread per-seed kwargs through `_seed_paths.seed_path_for` at
  comparison time (cloud + q3329 + cliff500 variants).
- **`scripts/confirm_v1_2._q3329_n90_group` + `_cliff_500_group`** —
  archive locations routed through `_seed_paths.seed_path_for` against
  `results/seeds/q3329/p1000_mt70/n090_beta30/` and
  `results/seeds/cliff500/q97/n130_beta40/` respectively.
- **`scripts/q3329_verify.SUMMARY_DIR`** — write target moved from the
  deleted `results/q3329/` to `results/seeds/q3329/summary/`.
- **`scripts/q3329_verify` q=97 baseline comparison** — glob-fallback
  chain replaced with a single `load_all_seeds(campaign="main")` call.
- **`examples/01_inspect_one_seed.py`**, **`examples/02_compare_two_groups.py`**,
  **`examples/03_plot_basis_profile.py`** — argparse gains `--campaign`
  (default `main`); inline `results/raw + results/cloud` fallback
  replaced with `load_all_seeds(campaign=, q=97)` manifest queries.
- **`paper/latex/sdbkz_paper_latex.tex` + `paper/sdbkz_paper.html` §Reproducibility** —
  one-paragraph addition documenting the seed-layout convention and
  pointing readers at `results/seed_path_crosswalk.csv` for pre-v2
  citation reconciliation. LaTeX rebuilt to 32 pages.
- **`COOKBOOK.md`** — three recipes rewritten to use
  `load_all_seeds(campaign=, q=97)` against the manifest instead of
  the deleted `glob.glob("results/raw/...")` pattern.
- **`.github/workflows/build-and-verify.yml`** — `Validate committed
  seed files` step rewritten to walk `results/seeds/<campaign>/` dirs
  rather than the deleted top-level legacy dirs.
- **`hash_verification.txt`** (both repo-root + `results/`) — footer
  block documents the canonical v2.0.0 seed path and the crosswalk CSV
  as the pre-v2 reconciler. SHA-256 hashes themselves are content-
  derived and remain bit-identical.

### Preserved (moved, not deleted, per CLAUDE.md never-delete rule)
- 10 pilot seeds `results/3x_tours/n60_beta30_seed{1..10}.json` →
  `results/seeds/tours3x/pilot/n60_beta30_seed{N}.json`.
- 8 summary JSONs from `results/3x_tours/` →
  `results/seeds/tours3x/summary/`.
- `results/q3329/summary_q3329.json` →
  `results/seeds/q3329/summary/summary_q3329.json`.
- `results/q3329_degenerate/README.md` →
  `results/seeds/q3329/q3329_degenerate_README.md`.
- `results/convergence/summary_convergence.json` →
  `results/seeds/convergence/summary/summary_convergence.json`.
- `results/convergence_test/summary_convergence.json` →
  `results/seeds/convergence/summary/summary_convergence_test.json`.

### Added
- **`tests/test_v2_path_migration.py`** (new, 8 cases) — static scan
  rejects any future `glob.glob` / `open` / `os.path.exists` /
  `os.listdir` / `os.scandir` reference to the 14 deleted directories;
  `_seed_paths.seed_path_for` contract assertions for the four
  campaign × (n, β) tuples touched in this migration; subprocess
  smoke against the three migrated example scripts.

### Added (pre-v2 changes that accumulated under the Unreleased
heading before the v2.0.0 layout work landed; carried over verbatim
into the v2.0.0 bundle since they ship in the same tag)

- **`config/sweep.toml`** (new top-level file) — single-source TOML
  capture of every campaign's `(n_grid, beta_grid, q, precision,
  tours_by_beta, num_seeds, store_per_tour)` tuple. Seven campaigns
  declared: `main` (paper sweep, 33-cell q=97 grid), `q3329`
  (ML-KEM modulus 1000-bit MPFR), `cliff500` (β=40 precision
  robustness at n=130, 500-bit), `convergence_beta40_mt1000`
  (eight-dim cliff bracket n=110..160), `convergence_beta30_mt1000`
  (β=30 trio), `tours3x` (3× tour budget capability test),
  `fplll_sensitivity` (5 seeds × 3 fplll versions). `inherits` keys
  let campaigns share base settings (e.g. all q=97 sets inherit
  from `main`).
- **`scripts/_config.py`** (new module) — TOML loader with strict
  validator. Returns a frozen `Campaign` dataclass per name; unknown
  keys, missing required fields, inheritance cycles, negative
  numerics, and a `tours_by_beta` mapping that fails to cover the
  `beta_grid` are all rejected with explicit `ConfigError`. Module
  docstring spells out the migration plan: this is a foundation
  surface; existing runner scripts continue to use their hardcoded
  constants until a future opportunistic touch migrates them. The
  per-seed JSON `campaign` + `config_version` provenance fields
  proposed in the backlog design doc are explicitly deferred (would
  break SHA-256 reproducibility chain).
- **`tests/test_config.py`** (new) — 22 pytest cases. Real-file
  layer round-trips the committed `config/sweep.toml` against the
  existing hardcoded constants in `sweep_parallel` / `q3329_verify`;
  synthetic layer exercises every validation branch (missing file,
  parse error, unknown root key, unknown campaign key, missing
  required, version mismatch, unknown campaign name, inheritance
  resolution, inheritance cycle, tours_by_beta coverage of
  beta_grid, negative q / precision / tours, empty grids,
  non-table default, load_all coverage). Full suite 181 → 203 cases.
- **`scripts/check_new_top_level_dirs.py`** allowlist gains
  `"config"` so the INC-39 pre-commit / CI guard accepts the new
  top-level directory.

### Changed
- **Paper §Limitations bracket sentence extended to eight dimensions.**
  Folds n=160 into the β=40 1000-tour bracket text that previously
  documented seven dimensions ({110, 120, 122, 125, 130, 140, 150}).
  Mean-advantage list at t=1000 grows to ${+}2.101, {+}0.159, {-}0.328,
  {-}1.038, {-}1.857, {-}2.420, {-}2.064, {-}1.788$; BKZ per-tour
  improvement softening trajectory grows to {+}1.06 / {+}0.92 / {+}0.74
  at n={140, 150, 160}; concluding sentence rewritten from "saturates
  rather than continuing to widen" to "saturates and then reverses",
  with the cliff bottom explicitly characterised as bottoming in the
  n=130-140 band and "unwinding toward broader convergence on either
  side". LaTeX rebuilt to 32 pages (same length); HTML resynced
  verbatim. Paper-figure parity gate clean. Deferred from v1.5.2 per
  the "data-only bundle" task plan; folded here for the v1.6.0 cut.
- **n=140 β=40 mt1000 fattened 20 → 100 seeds.** Holiday compute window
  on Windows host (13900K, WSL2 Docker, T0 2026-05-20 → T15 2026-05-30).
  Mean advantage tightens from −2.420 to −2.403 (Δ +0.017, within 20-seed
  CI); win rate 0/100 confirms cliff bottom. BKZ per-tour Δd(LN)
  70→1000 = +1.0295 (was +1.06); SD-BKZ Δ = −0.0514. Bracket vector
  updates to ${+}2.101, {+}0.159, {-}0.328, {-}1.038, {-}1.857, {-}2.403,
  {-}2.064, {-}1.788$; n=110→n=140 swing 4.52 → 4.50 nats; per-tour
  improvement +1.06 → +1.03 at n=140. Paper HTML + LaTeX §Limitations
  resynced; seed-count language now "20 seeds each at $n \in \{110,
  120, 122, 125, 130, 150, 160\}$ plus 100 seeds at $n=140$". Manifest
  4,741 → 4,821 entries; convergence campaign 260 → 340. Bit-identity
  verified across three environments (VMware VM native python, VMware
  VM Docker, WSL2 Docker) before T0 launch.

### Added (Phase 4 CI gates, held local on `phase4/ci-gates` branch
prior to this paragraph; merged to main 2026-05-20 via `5b5c2c4`)
- **`ci(mypy)`** strict mypy gate on `_math_core` + `_bkz_core` +
  `_runner_core` + `_signal_utils`. Pyproject `[tool.mypy]` config
  pins the four targets; CI step installs mypy + runs `python3 -m
  mypy` (Phase 4 #9; commit `0115da1`).
- **`ci(ruff)`** select expanded from `["F", "W", "I"]` to
  `["F", "W", "I", "B", "UP"]`; 138 violations fixed same-commit
  via `ruff check --fix` (127 safe) + `--unsafe-fixes` (11 B905
  `strict=False` additions). PL skipped — overlap with mypy strict.
  UP045 (Optional → X|None) deferred to a focused syntax pass.
  (Phase 4 #10; commit `1e771c4`).
- **`ci(coverage)`** pytest --cov 75% floor on the three
  numerical-core files; tree sits at 96.20%. `[tool.pytest.ini_options]
  pythonpath = ["scripts"]` so the bare module imports inside test
  modules resolve; `[tool.coverage.run] source = ["_math_core",
  "_bkz_core", "_signal_utils"]`. `tests/test_bkz_core_smoke.py`
  (8 cases, n=20 β=10 mt5 ~0.7s) + `tests/test_signal_utils.py` (10
  cases, mocked-Pool + signal-handler closure). Defensive `return`
  added after `os._exit` in `_signal_utils._handler` for test-mock
  flow safety. (Phase 4 #11; commit `eceeeae`).
- **`ci(figure)`** Figure-parity workflow step (`paper/fig*.png`
  byte-identity against `analysis/figures/`) was already in place
  pre-Phase 4 at `.github/workflows/build-and-verify.yml` lines
  203-233. No new step required. (Phase 4 #12; doc-only close-out
  in commit `96e934e`).

### Fixed — paper-integrity pre-tag pass (2026-06-02/03)

- **Seed-count alignment (C1).** Four variance-filled groups (n=100 β=30/40,
  n=110 β=40, n=130 β=40) now report 122 seeds (was a frozen 100) across Tables
  3/4/6/8, abstract, §6 body, captions, and conclusion in both the HTML and
  LaTeX manuscripts — matching the figures and `full_summary_33groups.json`.
  GSA recomputed at 3,388 main-sweep seeds (Pearson r=0.89 unchanged). Main-sweep
  total 3,300→3,388; manifest 4,741→4,821 (README/CITATION refreshed).
- **HF/RHF labelling (M1).** Corrected a false §3.2 claim that the implementation
  "converts to RHF at report time" — it reports the Hermite factor HF=δ^d
  directly; Table 3 column "RHF Δ"→"HF Δ"; §4 magnitude claims relabelled to HF.
  The RHF-blindness thesis is unchanged (monotone transform).
- **n=140 convergence framing (M4 + H1, 4 locations).** The n=140 β=30 crossover
  is now reported as significant at the 500-tour budget but a statistically
  undetectable underpowered null at 1000 tours (mean +0.029, 95% CI
  [−0.021, +0.079], 12/20, ≈0.21 power) across §5.3, Fig 5, §7.4, and §10; the
  robust high-dimension reversal is attributed to n=150.
- **Figure coverage + gate.** fig8 (dln_vs_rhf) title corrected 100→122 seeds;
  `paper/latex/figs/` byte-synced to `analysis/figures/`; the missing Figure 12
  (per_position_landscape) added and q3329 renumbered Figure 13; the figure-parity
  CI gate extended to cover BOTH the HTML bundle and `paper/latex/figs/` (26 pairs).
- **Docs truthed (M6) + abstract framing (B1–B3).** fplll PR #550 stated as
  closed-unmerged; 3×-tour claim scoped to β≥30 with the β=20 partial-close
  caveat; one-clause attractor-open hedge on the intro fixed-point claim; an
  unverifiable SONAME parenthetical dropped; "more than 4,500 seeds" aligned
  across channels.
- **PDF rebuilt.** `paper/latex/sdbkz_paper_latex.pdf` regenerated from the
  corrected LaTeX (was a stale 2026-05-20 build) and verified to carry every fix
  with no stale values.

## [1.5.2] — 2026-05-19

### Added
- **n=160 β=40 mt1000 cell** — 20 seeds at q=97, 250-bit MPFR, 1000
  tours under `results/seeds/convergence/q97/n160_beta40_mt1000/`.
  Mean advantage at t=1000 = −1.788 nats (range [−2.225, −1.542],
  win rate 0/20). t=70 adv −1.095; t=500 adv −1.585; t=1000 adv
  −1.788 — descent continues with tour budget in BKZ's favour.
  BKZ per-tour Δ d(LN) t=70→1000 = +0.741 nats; SD-BKZ = +0.048
  (essentially flat). The cliff trajectory at t=1000 across the
  full eight-dimension bracket now reads
  +2.101 / +0.159 / −0.328 / −1.038 / −1.857 / −2.420 / −2.064 /
  −1.788 across n ∈ {110, 120, 122, 125, 130, 140, 150, 160} —
  cliff bottom firmly localised to the n=130–140 band, with n=150
  and n=160 both shallower (BKZ per-tour improvement also
  decreases monotonically: +1.06 / +0.92 / +0.74 at n=140 / 150 /
  160). n=160 confirms the v1.5.1 "bounded-extent cliff" framing
  rather than extending the claim. Per the v1.5.1 → v1.5.2 task
  plan this was originally scoped as a **data-only bundle** with no
  paper §Limitations edit. The bracket-text update was folded in
  post-v1.5.2 in commit `d79584a` ("paper: §Limitations bracket
  extended to eight dims (n=160 fold-in)") and carried forward into
  the v2.0.0 candidate; the original "no paper text edit" claim
  reflected the v1.5.2 cut point only. Manifest 4,721 → 4,741 (+20
  entries); convergence campaign 240 → 260. README seed totals
  bumped in three places.
- **Estimator extrapolation + monotone clamp** (carried over from
  the v1.5.1 → v1.5.2 cycle since it landed on `main` after the
  v1.5.1 tag was cut) — `scripts/seed_timing._lookup_cost` now
  interpolates / extrapolates per-tour cost from adjacent-dim
  same-β anchors, with a monotone-non-decreasing floor in the
  extrapolate-above case. Sweeps at dimensions absent from the
  per-tour cost cache no longer return `predicted_wall_h=None`.
  Two follow-up commits tighten the implementation: a self-review
  pass adds the monotone clamp + improves the note wording; a
  deeper review pass closes UTF-8 encoding (`bug 5`), tours-run
  fallback (`bug 6`), stale-anchor field leakage (`bug 9`),
  zero-seed pool (`imp 13`), cache-mtime equality (`imp 16`),
  and schema_version validation (`imp 17`). Estimator predicted
  80h for n=160; observed 83.5h (within 4%). 10 new pytest cases
  on top of the original 16 (full suite 144 → 164).

## [1.5.1] — 2026-05-16

### Added
- **n=150 β=40 mt1000 cell** — 20 seeds at q=97, 250-bit MPFR, 1000
  tours under `results/seeds/convergence/q97/n150_beta40_mt1000/`.
  Mean advantage at t=1000 = −2.064 nats (range [−2.536, −1.703],
  win rate 0/20). t=70 adv −1.180; t=500 adv −1.783; t=1000 adv
  −2.064 — descent continues with tour budget but in BKZ's favour.
  BKZ per-tour Δ d(LN) t=70→1000 = +0.918 nats; SD-BKZ = +0.034
  (essentially flat). Material finding: cliff is **non-monotone past
  n=140** — n=150 is shallower than n=140 (−2.420) by 0.36 nats and
  BKZ per-tour improvement softens from +1.06 (n=140) to +0.92
  (n=150). The cliff bottoms in the n=130–140 band within the tested
  range. Paper §Limitations sentence rewritten in
  `paper/latex/sdbkz_paper_latex.tex` and `paper/sdbkz_paper.html`;
  LaTeX rebuilt to 32 pages (up from 31; ~one-paragraph extension).
  Bracket grows from six to seven dimensions in the §Limitations
  enumeration. Asymmetry direction (BKZ improves with tours, SD-BKZ
  does not) holds throughout the tested range; only the magnitude
  monotonicity claim is updated. Seed manifest 4,701 → 4,721
  (+20 entries); convergence campaign 220 → 240 seeds. README seed
  totals refreshed in three places (TL;DR, highlights, mermaid).
- **Dockerfile digest pinning + apt via snapshot.debian.org** (ADR-004,
  `docs/design_decisions.md`). All four Dockerfiles (`Dockerfile`,
  `Dockerfile.cloud`, `Dockerfile.fplll54`, `Dockerfile.fplll_legacy`)
  now pin the base image to
  `python:3.12.3-bookworm@sha256:25dee7f137aa44c4962d21346385737eb81954b6f06f519fcc348b67f6483d3c`
  and rewrite `/etc/apt/sources.list.d/debian.sources` to
  `snapshot.debian.org/archive/debian/20240614T000000Z/` before the
  libmpfr-dev / libgmp-dev / build-essential install. Together the
  two anchors guarantee that a future rebuild resolves to the same
  byte set as the v1.5.x reference environment regardless of upstream
  tag reflows or Debian revision rolls. `scripts/verify.sh` header
  records the digest + snapshot date so the reproducibility chain is
  self-describing. Dry-run gate: `docker build -t sdbkz:phase2-test .`
  → `docker run --rm -e NUM_SEEDS=1 sdbkz:phase2-test bash
  scripts/verify.sh` returns `VERIFICATION PASSED` with seed 1
  advantage=0.211363 matching reference.
- **`docs/audits/2026-05-14_zenodo_v1.5.0_contents.md`** — Zenodo
  concept DOI `10.5281/zenodo.19686928` deposit content audit.
  Confirms `results/seeds/` (4,541 JSONs, all >100 bytes),
  `results/seed_manifest.json` (matching count),
  `results/seed_path_crosswalk.csv`, and `sdbkz_paper_latex.pdf` are
  intact. Documents the literal threshold drift (tasking gate cited
  4,701; deposit has 4,541 because the additional ~160 post-flip
  seeds landed after the 2026-04-22 archival snapshot) and the
  inconclusive OpenAIRE index probe at 22 days post-publish.
  Non-blocker for v1.5.1 tag.
- **`analysis/_stats_helpers.py`** (new module) — `cliffs_delta()` and
  `holm_bonferroni()` helpers backing the v1.5.1 paper-table refresh.
  `cliffs_delta` returns the one-sample distribution-free effect size
  `(#wins − #losses) / n` against the constant zero; `holm_bonferroni`
  applies the Holm step-down adjustment over a p-value family while
  preserving input order and passing `None` entries through. Pure-
  input pure-output; no SHA-256 schema mutation. ADR-003 in
  `docs/design_decisions.md` records the choice of Holm over BH.
- **`docs/design_decisions.md` ADR-003** — "Multiple-comparison
  correction over the 33-cell main grid (v1.5.1)". Justifies Holm vs
  BH on small-family + asymmetric-cost + no-dependence-assumption
  grounds; explains why Cliff's δ is added alongside Cohen's d rather
  than replacing it.
- **`tests/test_stats.py`** (new) — 19 pytest cases covering Cliff's δ
  edge cases (all-win, all-loss, all-tie, empty, balanced, majority,
  ties dilute, sign matches mean direction, range bound) and Holm
  correctness (monotonicity, input-order preservation, smallest-equals-
  Bonferroni for rank 1, cap-at-one, equal-p case, strict-dominance
  over Bonferroni in the mixed case, `None` pass-through, all-`None`,
  empty, family-of-one).
- `analysis/stats_analysis.py` + `analysis/tables.py` — both now compute
  and render Cliff's δ alongside Cohen's d and raw + Holm-adjusted
  p-values alongside the raw t-test and Wilcoxon columns. The
  correction families are the rendered row set (33 cells for the main
  campaign), corrected independently per p-value column.
- `analysis/stats_analysis.py` — gains a `--campaign <name>` argparse
  flag (default `main`); the default invocation now reads the v1.3
  manifest in manifest mode rather than the legacy `results/raw/` dir,
  matching the v1.5.0 paper-claims file generation path.
- **`results/paper_claims/full_stats_33groups.txt`** — regenerated with
  raw + Holm-adjusted p-value columns and a Cliff's δ column. Bit-
  identity gate: pre-correction p-values match v1.5.0 within the
  baseline TXT rendering precision (10/10 cells on the `results/raw/`
  subset verified post-change).
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
- **`.github/dependabot.yml`** — Dependabot config covering pip
  (pyproject.toml), docker (4 Dockerfiles), and github-actions
  (workflow versions). Weekly Monday cadence; minor + patch updates
  grouped per ecosystem. Numerical-core pins (`fpylll`, `cysignals`,
  `numpy`) explicitly ignored — paper-safety SHA chain forbids
  silent bumps; bumps must be manual + paired with `verify.sh` re-anchor.
- **`.github/workflows/scorecard.yml`** — OpenSSF Scorecard workflow.
  Weekly Mon 06:00 UTC + push to main + branch-protection events +
  manual dispatch. SARIF upload to GitHub Security tab + public
  viewer at `securityscorecards.dev/viewer/?uri=github.com/...`.
  Action versions use semver tags initially; Scorecard's own
  Pinned-Dependencies check will recommend exact commit SHAs in
  the first report (re-pin in a follow-up to those verified hashes).

### Changed
- **Docker images now run as non-root.** All four Dockerfiles
  (`Dockerfile`, `Dockerfile.cloud`, `Dockerfile.fplll54`,
  `Dockerfile.fplll_legacy`) create a `runner` user matching host
  UID/GID via `--build-arg HOST_UID=$(id -u) --build-arg
  HOST_GID=$(id -g)` (defaults `1000:1000` for the common Linux
  desktop case). `COPY --chown` and a final `chown -R` ensure
  bind-mounted `./results` + `./logs` no longer produce root-owned
  host files (Incident #32 closed). `docker-compose.yml` injects
  `${UID:-1000}` / `${GID:-1000}` automatically;
  `.github/workflows/build-and-verify.yml` resolves runner UID/GID
  dynamically and feeds it as build-args. README Troubleshooting
  section gains a non-root override hint for non-1000 UID/GID hosts.
- **`Dockerfile`** main image is now self-contained: ships
  `analysis/`, `tests/`, `results/paper_claims/`, and the seven
  paper-cited `results/*.json` files (`summary`, `runtime_table`,
  `profile_decomposition`, `convergence_headroom`, `dGSA_summary`,
  `seed_manifest`, `hash_verification.txt`). A reviewer can now
  `docker run sdbkz-benchmark:ci python3 -m pytest tests/` or
  `docker run sdbkz-benchmark:ci python3 analysis/paper_figures.py`
  without bind-mounting the host repo. Bulk seed data stays out of
  the image via `.dockerignore`. Image size delta ~11 MB (well under
  the 50 MB budget). Closes INC-36 from the 2026-04-20 fresh-VM
  reproducibility audit. Also adds an MPFR-version comment near the
  base image line so an auditor sees that 4.2.0 vs 4.2.1 drift
  across reference environments is accounted for, not silent.

### Added (post-flip continuation)
- **β=40 1000-tour bracket — six dimensions** at q=97 250-bit MPFR,
  20 seeds each: `n ∈ {110, 120, 122, 125, 130, 140}` under
  `results/seeds/convergence/q97/n{n}_beta40_mt1000/`. Mean
  advantages at t=1000 are +2.101, +0.159, −0.328, −1.038, −1.857,
  −2.420 — a 4.52-nat swing across Δn=30. Crossover dimension
  localised to the interval (n=120, n=122) (Δn=2 bound; win rate
  drops 19/20 → 0/20 in two dimension steps). n=122 is invariant
  to tour budget (advantage at t=70 and t=1000 coincide within
  noise). The cliff deepens monotonically past n=130 (BKZ per-tour
  improvement +0.18 at n=125, +0.49 at n=130, +1.06 at n=140 nats
  over t=70→t=1000; SD-BKZ plateaus or slightly degrades at all
  three). The bracket data confirms the β=40 cliff is a structural
  dimension-dependent regime change, not a finite-tour or
  fixed-magnitude artifact. Manifest grew 4,432 → 4,701 entries
  across the v1.5.x window (+269 follow-up seeds since paper-frozen
  v1.5.0). Commits `ccc9674` + `dec8a1b`.
- **fplll upstream PR `#550`** filed 2026-05-08. Single-commit
  patch (`ebcedf53`) on branch `fix/gso-kahan-cancellation` in the
  `BrendanChambersBourgeois/fplll` fork. Passes 15/15 `make check`;
  `make check-style` clean under clang-format 18 (matching the apt
  version on `ubuntu-latest`). PR body cites the Zenodo DOI for
  per-seed evidence + reproducer. Doc updates synchronise the
  status across `ROADMAP.md` (External waits: ⏸ → ✅),
  `docs/disclosure/fplll_gso_kahan_findings.md` (timeline gains a
  2026-05-08 row), and `patches/README.md` (Status section).
  Commit `c9882b4`.

### Paper
- **§Limitations rework** — extends the existing post-v1.5.0
  1000-tour paragraph with two new data blocks: (a) a β=30 trio
  (n=90 mt1000 already covered; adds n=140 deficit-dissolves and
  n=150 deficit-deepens), and (b) the β=40 six-dimension mt1000
  bracket with the 4.52-nat swing and the Δn=2 crossover
  localisation. Also updates §8.3 *Mitigation and Upstream Context*
  to recontextualise the fplll #237 reference (meta-issue on
  numerical-stability test coverage, not the cancellation locus
  itself) and to cite the new fplll PR `#550`. LaTeX source +
  rebuilt PDF; HTML stale until next sync. Commit `bedf1be`.

### Type-hint coverage (audit A20 — library tier)
- **`analysis/_data.py`, `scripts/_runner_core.py`, `scripts/log.py`**
  fully annotated. Public-API named aliases (`SeedDict`, `GroupKey`,
  `Groups`) in `analysis/_data.py`. Commit `e338ead`.
- **`scripts/sweep_parallel.py`, `scripts/validate_seeds.py`** —
  worker pool + seed validator fully annotated. Commit `06ebe34`.
- **`scripts/sweep_cloud.py`** — cloud worker pool fully annotated
  (decommissioned but kept for reproducibility). Commit `935be8b`.
  Library tier reaches 100% annotated; entry-point + test tiers
  remain `opportunistic on touch` per the audit disposition.

### Fixed
- **Docker image dependency pinning** — `matplotlib==3.10.8` plus
  PNG-render transitive deps (`pillow==12.2.0`, `fonttools==4.62.1`,
  `contourpy==1.3.3`, `kiwisolver==1.5.0`, `pyparsing==3.3.2`,
  `cycler==0.12.1`) pinned in `Dockerfile` and `Dockerfile.cloud`
  alongside the existing `fpylll`/`cysignals`/`numpy`/`scipy` pins.
  Root cause: figure-SHA byte-identity gate failed in CI on commit
  `ccc9674` because the fresh-build matplotlib bumped 3.10.8 →
  3.10.9 and PNG byte output drifts at patch level (text rendering,
  anti-alias, metadata). `verify.sh` and the paper-figure parity
  gate stayed green throughout — only the regen-vs-baseline gate
  catches matplotlib drift. Local validation: rebuilt image
  produces baseline-matching SHAs across all 14 figures (sorted
  diff empty). Closes the unflagged pip-side counterpart to audit
  A27's apt-side commentary. Commit `e7936c5`.

### Closed audit items (v1.5.x doc-only group)
- **A31** — `scorecard.yml` actions re-pinned from semver tags to
  commit SHAs (`actions/checkout`, `actions/upload-artifact`,
  `ossf/scorecard-action`, `github/codeql-action`); header comment
  rewritten with refresh-on-bump instructions. Commit `a4a0843`.
- **A33** — `CONTRIBUTING.md` onboarding gains a pre-INC-32
  rebuild note: stale local images still run as root and produce
  root-owned bind mounts; rebuild with
  `--build-arg HOST_UID=$(id -u) --build-arg HOST_GID=$(id -g)`
  after pulling INC-32 fix. Commit `49890db`.

### Removed
- **`scripts/health_check.sh`** — dormant cron probe retired
  2026-04-07 when the local sweep finished and the cloud took over
  (per the script's own header). No callers anywhere in the repo;
  README §scripts entry dropped alongside. Backup retained offline
  at `_archives/health_check.sh.dormant_2026-04-25.bak`
  per the never-delete-without-backup rule. INC-39.
- **`logs/convergence_n{90,140,150}_mt1000_stdout.log`** +
  **`logs/convergence_n150_mt1000_stdout.log.pre_refactor`** —
  legacy stdout captures from completed sweeps. Tarball + SHA-256
  manifest retained offline at
  `_archives/logs_legacy_2026-04-25.tar.gz`
  (SHA-256 in `_archives/CHECKSUMS_legacy_2026-04-25.sha256`; audit chain stays out
  of the public repo per INC-39). `logs/` now contains only
  `pipeline.jsonl` (authoritative), `.gitkeep` (placeholder), and
  the in-flight n=130 β=40 mt1000 sweep stdout (which will be
  archived to the same offline location after that sweep completes).
- **`_archives/`** directory — added then reverted in the same
  Unreleased window, then **scrubbed from git history via
  `git-filter-repo` + force-push** (INC-39 escalated to critical;
  bounded scrub preserved v1.5.0 / Zenodo correspondence intact).
  Originally added in the commit now `90d118d` (was `0c85b5f`
  pre-rewrite); reverted in the commit now `09b6e81` (was `d541129`).
  Internal audit chain belongs offline, not in the public-facing
  reproducibility surface. Now `.gitignore`d so future archive
  tarballs stay local by default. Pre-rewrite repo bundle preserved
  offline at `_archives/sdbkz_pre_inc39_rewrite_2026-04-25/`.
  INC-39.

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
  (24K).** All 19 files archived **offline** to
  `_archives/logs_legacy_2026-04-20.tar.gz`
  with SHA-256 in the adjacent `CHECKSUMS.sha256` before rm. (Audit
  chain lives offline by convention — the in-repo `_archives/` path
  is `.gitignore`d per INC-39, 2026-04-25.) `logs/` retains
  `pipeline.jsonl` + `.gitkeep` + active stdout captures only.
- **Empty dir `results/3x_tours_extended/`** — scaffold never
  populated, rmdir.
- **Byte-identical duplicate `results/paper_claims/profile_decomposition.json`**
  (paper-cited canonical is `results/profile_decomposition.json`).
  Archived dup **offline** at
  `_archives/profile_decomposition_paper_claims_dup_2026-04-20.tar.gz`.

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
