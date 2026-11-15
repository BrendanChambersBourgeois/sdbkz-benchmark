# Changelog

User-visible changes per version. Seed counts are manifest totals.

## Unreleased

### Added
- Paper 1 claims ledger (`make paper1-claims`, `results/paper_claims/paper1_claims.json`) with a test tying printed numbers to the seeds.
- Paper 1 claims ledger covers the main, statistics, decomposition, growth, peak and q=3329 tables and the convergence sentences.
- Campaign `ntru_equal_sweep`: BKZ-only legs that record the tour of the first exact key match.
- Seed tree `results/seeds/ntru_equal_sweep/` (120 seeds; side manifest 10,073).
- Frontier collapse counts from the basis prefix (`make paper2-claims`, `results/paper_claims/frontier_prefix_volume.json`).
- Paper 2 frontier section: prefix-collapse table, with ledger records.
- `results/profile_decomposition.json`: d(LN) advantage split between the profile body and its last beta log-norms, with body slopes.

### Fixed
- Paper 1 Figure 8: the GSA line uses the standard slope; the caption states what the figure shows.
- Paper 1: block size 40 is level with 30 at n=110; the tour-cost sentence cites the 3x-tour runs. Paper 2 abstract: onset gap under a monotone fit.
- Paper 1: six printed numbers corrected against the seeds (two confidence bounds, a standard deviation range, two trend values, one decline).
- `extract_dsd_onset.py` counts one file per seed, the highest precision. Paper 2 profiles figure plots 1-based positions.
- Loader tests restore the manifest path they repoint.
- Paper 2 Figure profiles: legend names the mean secret log-norm; caption states the precision per panel.
- Figure code: paired-keys reads seed files in sorted order, peak-dip counts seeds with a profile, the R² fit stops on an empty cell; a test ties figure onset constants to the claims tables.
- `analysis/_data.py`: a seed file a loader cannot read, or a convergence file without per-tour keys, is logged (path and error) and counted before it is skipped.
- Paper 1 Figure 12 re-rendered: title and labels describe the double-precision measurement, 100 seeds; caption spike range.
- Paper 2: floored-leg and all-ones-leg counts updated to the current seed set.
- CONTRIBUTING: `make verify` step list.
- Paper 1: β=40 peak stated as n=100–110, measured compute premium, RHF table cells, test labels and outlier-seed counts corrected.
- Paper 2: four sentences reworded to match the per-key counts and the β=50 ladders.
- Paper 1: peak ordering across block sizes, cliff steepness, dip location, extra-tour gap and q=3329 range reworded to match the stored seeds; rounding and standard-deviation convention aligned with the tables.
- Paper 2: Figure caption seed counts for the exact-recovery brackets.
- `analysis/tables.py`, `analysis/stats_analysis.py`: Wilcoxon test is two-sided, as the paper states.
- 2.1.0 notes: the JOSS draft (`paper.md`, `paper.bib`) and the `[cloud]` extra were added and removed before the release and are not in it; `boto3` is no longer a dependency.
- 2.1.0 notes: the CI `validate_seeds` list covers every seed tree except `ntru_flatter` (deferred); `tours3x` is checked non-strict.
- README results table states its seed range (seeds 1–100; the paper's tables use all 122 in four cells).
- `docs/seed_manifest_schema.md`: example rollup, pinned timestamps, side manifest and crosswalk text match the tree.
- `docs/images.md`: worklists reference dropped; `Dockerfile.fplll_legacy` listed.
- `results/paper_claims/full_stats_33groups.txt` regenerated from the committed seeds with the two-sided Wilcoxon test.
- `analysis/stats_analysis.py`: a test statistic or p-value of zero is printed, not shown as N/A.
- Paper 2 claims ledger: the two-sided sign-test p-value is capped at 1 when the counts tie.
- Paper 2 claims ledger: a frontier seed with a null exact-match field stops the build instead of counting as a failed recovery.
- Paper 1: the position-93 comparison and the β=40 and β=30 peak values match the plotted data (all seeds).
- Paper 2: the tour-budget figure text gives tour 30, where SD-BKZ flattens its second block and the flag fires.
- q=3329 MPFR n=90 summary named per cell, like its siblings.
- `analysis/runtime_table.py` no longer writes the dropped `runtime_table.html`.
- q=3329 degeneracy figure computes its win-rate label from the data.
- `docs/seed_manifest_schema.md` tag list includes `extended`.
- Paper 2 paired-keys figure counts one cell per (q, seed) when a seed was rerun at a higher precision; no plotted count changes.
- Paper 1: standard-deviation cells of the main and peak tables use the sample standard deviation throughout.
- `analysis/runtime_table.py`: averages seeds 1–100, as the paper's runtime table does; captions state the per-β tour budget.
- Paper 2 claims ledger: records added for the β=20 onset table, its exact-recovery gap intervals, the per-key counts and the dimension-onset means; interval records match at the printed precision.

## [2.1.0] — 2026-11-12

### Added
- Paper 2 figures: raw Gram-Schmidt profiles and frontier recovery curves and a per-tour profile heatmap added; phase map dropped; abstract leads with the onset gap.
- Paper 2 PDF tracked at `paper2/latex/sdbkz_paper2.pdf`, built from the `.tex` beside it.
- `results/side_seed_manifest.json` (`make manifest-side`): SHA set of the auxiliary trees, 9,953 seeds, gated like the patched manifest.
- G6K reject-on-overflow build (`patches/g6k_gauss_reject_overflow.patch`, `Dockerfile.g6k` `REJECT_OVERFLOW`, tag `sdbkz-g6k:dim384-reject`) and the rerun campaigns on it: β=60 ladder, β=50 frontier n=179–185, n=179 β=40 deep-tour controls, vecprobe seeds; tree `results/seeds/ntru_g6k_reject/` and `ntru_g6k_vecprobe_reject/`.
- Exact-field reruns of the flag-scored NTRU cells (`ntru_exact`, `ntru_g6k_exact`) recording `secret_exact_match`.
- q=3329 cells re-measured with an MPFR measurement GSO (`q3329_mpfr`); `store_bases` flag and `scripts/check_bases_exact.py` for exact integer checks of saved bases.
- n=127 cells rerun on the sign-corrected Kahan build (`ntru_patched_kahan_v3`); patched manifest 224.
- g6k as a second reduction engine (`scripts/_engine_backends.py`), self-dual pump-BKZ variant, G6K manifest and lint, `scripts/compare_xengine.py`.
- NTRU β=20 ball-out (1,858 seeds, 57 cells); `scripts/extract_dsd_onset.py`; `store_short_vectors` and `scripts/vecprobe_membership.py`; `sieve_trace` flag.
- `scripts/_seed_io.py`: atomic seed writes, resume validation, corrupt quarantine in every runner.
- `make image-*` targets and `docs/images.md`; campaign `image`, `backend`, `seed_tag` keys.
- `Dockerfile.g6k` `ISA` build arg (tag `sdbkz-g6k:dim384-inc63-fma`) and a multi-tour NTRU golden in `scripts/verify_g6k.sh`.
- JOSS draft `paper.md`, `paper.bib`, `CODE_OF_CONDUCT.md`.
- Seeds: fplll manifest 14,669; G6K manifest 3,034.

### Changed
- Paper 2: frontier section, exact secret-match scoring, Paper 1 corrections appendix, reject-build rows, n=163 at 100 seeds.
- Paper 2: n=157 at 100 seeds, key-resampled onset-gap intervals, per-core-hour ratios with intervals.
- Paper 2: exact key recovery onsets beside the DSD flag onsets; scope and subset statements corrected; phase figure gap label.
- Paper 2 coverage table includes the native-fplll β=40 ladders; claims ledger scope follows.
- Paper 1 §8 rewritten: the q=3329 floors were our double-precision measurement, not fplll; 1000-bit advantages at n=80–100; patch claim withdrawn.
- Paper 2: key-clustered frontier tests, Paper 1 §8 statements added to the corrections appendix, crossover means without measurement spikes, figure text matches the captions.
- Paper 2: precision and build statements per engine, composite-n note, missing 200-tour frontier row; claims ledger covers it.
- `extract_dsd_onset.py` and `onset_driver.py` score `secret_exact_match`; all-ones-vector legs no longer count as recovered; trend gap from unrounded onsets.
- `estimate_sweep_time.py`: early-stop and precision-aware estimate, `--backtest`.
- `run_campaign.py --start/--end` reach every runner; NTRU task tuples validated; g6k campaigns re-exec inside the image when the host lacks g6k.
- CI: strict `validate_seeds` list covers every tree, read-only token permissions, pinned tools, `g6k-verify` as a hard byte-identity gate.
- DSD criterion finalised as the n-dependent two-part test.
- `paper/` renamed to `paper1/`; `boto3` moved to the `[cloud]` extra.
- Comments, docs and tests trimmed to what the code and data need; README, CHANGELOG, CONTRIBUTING, SECURITY and `docs/` rewritten short.

### Fixed
- `onset_driver.py` checks the campaign's generator, seed tree and measurement float type, and exits 3 when every traced n is abandoned.
- `results/profile_decomposition.json` regenerated by `make decomposition` from `analysis/tables.py` (shares of magnitude, largest region by magnitude); Paper 1 Table 5 and Figure 6 captions.
- Paper 1 §8: the −345 floors are attributed to the double-precision measurement GSO, not fplll; the Kahan patch result is withdrawn (README, SECURITY.md, `paper.md`, Paper 2 Appendix A).
- g6k CI SIGILL on x86-64-v2 runners (`--disable-native`); fplll Kahan patch sign.
- `_pidlock` reclaim race; single-instance lock shared by `forever_runner` and `onset_driver`; capped scheduler records native worker crashes.
- `validate_seeds.py --strict` fails on a missing listed directory; large NTRU volume drift labelled as the clamp sentinel.
- `q3329_verify.py` one summary per cell; `--start`, `store_per_tour` and the MPFR metric forwarded from `run_campaign.py`.
- `results/dGSA_summary.json` regenerated over the full main sweep; `CITATION.cff` concept DOI.

### Removed
- `paper1/sdbkz_paper.html` and its figure bundle (no generator; carried the withdrawn §8); the LaTeX PDF is the Paper 1 text.
- fplll Kahan and reorder-control patches, `Dockerfile.fplll_patched`, the fplll disclosure doc.
- Runner worklists, node unit files, roadmap, audit notes, archived scripts, `COOKBOOK.md`, `scripts/README.md`, `paper2/paper2_findings.md`; git history keeps them.
- Decommissioned cloud path (`sweep_cloud.py`, `submit_jobs.py`, `cloud_watchdog.sh`, `Dockerfile.cloud`, `[cloud]` extra), node tooling (`forever_runner.py`, `node_sync.py`, `node_status.py`, `make node-*`), one-off scripts (`migrate_seeds_to_new_layout.py`, `run_sweep_fill.py`, `overnight_experiments.py`, `find_bugs_via_tags.py`), the top-level `hash_verification.txt` duplicate, `results/runtime_table.html`, the scorecard and dependabot workflows, the JOSS draft (`paper.md`, `paper.bib`), `examples/` and the `results/summary.json` rollup (regenerated by `sweep_parallel.py --summary`).

## [2.0.0] — 2026-06-03
- 4,387 back-compat symlinks across 14 legacy top-level directories removed; `results/seed_path_crosswalk.csv` maps old paths to `results/seeds/<campaign>/`.
- `config/sweep.toml` + `scripts/_config.py` single-source campaign config; `scripts/run_campaign.py` dispatcher replaces six launcher scripts.
- CI gates: strict mypy on the numerical core, ruff F/W/I/B/UP, pytest coverage floor 75%, figure parity.
- Paper 1 pre-tag integrity pass: seed counts aligned (122-seed cells), HF/RHF labelling, n=140 convergence framing, PDF rebuilt.
- n=140 β=40 mt1000 fattened to 100 seeds.

## [1.5.2] — 2026-05-19
- n=160 β=40 mt1000 cell (20 seeds); estimator extrapolation with monotone clamp.

## [1.5.1] — 2026-05-16
- n=150 β=40 mt1000 cell (20 seeds); Holm correction over the 33-cell grid (ADR-003).
- Docker base image digest-pinned, apt via snapshot.debian.org (ADR-004).

## [1.5.0] — 2026-04-22
- Zenodo concept DOI 10.5281/zenodo.19686927; `CITATION.cff`; paper content refresh.

## [1.3.1] — 2026-04-19
- +25 q=3329 seeds at 1000-bit MPFR across intermediate dimensions; manifest builder tests.

## [1.3.0] — 2026-04-19
- Seed manifest (`results/seed_manifest.json`, SHA-256 per seed) and campaign tree under `results/seeds/` (ADR-002).

## [1.2.0] — 2026-04-18
- `_math_core` + `_bkz_core` + `_signal_utils` shared numerical core (ADR-001), byte-identical to v1.1.0.

## [1.1.0] — 2026-04-18
- iacrj LaTeX port of the paper; Kahan GSO patch shipped (later withdrawn).

## [1.0] — 2026-04-14
- Main q=97 sweep complete at 100 seeds per cell; gap-filler and q=3329 runner flags.
