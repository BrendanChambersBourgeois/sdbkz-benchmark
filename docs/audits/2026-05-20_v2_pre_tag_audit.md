# v2.0.0 pre-tag audit — six-subagent investigation

**Date:** 2026-05-20
**Trigger:** end-of-cycle bug + value audit on local v2.0.0 candidate (12 unpushed commits on `main`) before tag/push.
**Method:** six parallel Explore subagents, each auditing one surface, with strict "collect evidence, do not fix" mandate. Findings collated below.

## Subagent topology

| # | surface | findings |
|---|---------|----------|
| 1 | Python correctness (scripts/, analysis/, examples/) | 7 |
| 2 | Test coverage gaps (tests/ vs production surface) | 22 |
| 3 | Documentation + paper drift (README/CHANGELOG/ROADMAP/COOKBOOK/paper LaTeX+HTML) | 7 |
| 4 | Data integrity + SHA chain (manifest, crosswalk, hash_verification, paper_claims) | 3 |
| 5 | CI / build / Dockerfile / pyproject / dependabot | 11 |
| 6 | v2.0.0 migration completeness (functional residue post-rm) | 3 |
| **total** | | **53 raw, ~49 after dedup** |

## Severity tally (post-dedup)

- **Critical:** 4 (PY-001 resource leak; TEST-001/002/003 sweep_cloud zero coverage; V2-001 cloud_watchdog S3 prefix)
- **High:** 11
- **Medium:** 14
- **Low / informational:** 20

Two duplicate findings dropped: BUG-V2-002 ≡ BUG-DATA-003 (verify.sh RAW_DIR mkdir on deleted dir), BUG-PY-001 ≡ BUG-PY-003 (file-handle leak at lines 447 and 467 of analysis/_data.py — same root cause).

---

## CRITICAL findings (4) — must address before tag

### BUG-PY-001: File-handle leak in analysis/_data.py `_load_convergence_files`
- **File:line:** `analysis/_data.py:447, 467`
- **Pattern:** `json.load(open(path))` without context manager; file handles never closed
- **Risk:** Over hundreds of files per analysis pass, exhausts FDs → loader fails halfway, paper figures regen partial
- **Effort:** <5 min (wrap with `with`)
- **CLOSED 2026-05-20 (commit `03bdd17`)** — both call sites wrapped in `with open(path) as _fh`.

### BUG-V2-001: `scripts/cloud_watchdog.sh` S3 prefix hardcoded to deleted `results/raw/`
- **File:line:** `scripts/cloud_watchdog.sh:183, 185`
- **Pattern:** `S3_PREFIX="results/raw/n${N}_beta${BETA}..."`
- **Risk:** If cloud is ever restored, watchdog reports all jobs idle (pattern never matches the new `results/seeds/<campaign>/...` S3 prefix) → false-positive job termination
- **Effort:** 10 min (route through `_seed_paths.seed_dir_for` like sweep_cloud.py did)
- **Detector gap:** test_v2_path_migration.FUNCTIONAL_RE only scans .py files; shell scripts escape
- **CLOSED 2026-05-20 (commit `03bdd17`)** — S3_PREFIX rewritten to `results/seeds/q3329/p${PRECISION}_mt${MAX_TOURS}/...` and `results/seeds/main/q97/...` at lines 192/196; explanatory comment block lines 182-188.

### GAP-TEST-001: `scripts/sweep_cloud.py` S3 ops (upload, validate, list_completed) — **zero tests**
- **Code:** `scripts/sweep_cloud.py:119–180`
- **Surface:** S3 upload + JSON validation + corrupt-file deletion + completed-list scanning
- **Risk:** Silent data loss (corrupt uploads deleted without notification); resumption logic broken if list_completed returns wrong counts
- **Effort:** ~2h (mock boto3, hand-craft S3 responses)

### GAP-TEST-002: `scripts/sweep_cloud.py` watchdog thread + sigterm handler — **zero tests**
- **Code:** `scripts/sweep_cloud.py:66–103`
- **Surface:** global signal.signal + threading.Lock + os._exit(42) on timeout
- **Risk:** Watchdog fails silent (process hangs); SIGTERM handler not registered; partial JSON writes
- **Effort:** ~1.5h (mock time + threading)

(Note: GAP-TEST-001 + GAP-TEST-002 + GAP-TEST-003 are different aspects of the same `sweep_cloud.py` zero-coverage block.)

---

## HIGH findings (11)

### Python correctness
- **BUG-PY-007** — `analysis/_data.py:448` exception clause catches `(FileNotFoundError, json.JSONDecodeError)` but misses `KeyError` on the immediately-following key access at line 450. Silent data loss on schema mismatch. **CLOSED 2026-05-20 (commit `03bdd17`)** — except clause now `(FileNotFoundError, json.JSONDecodeError, KeyError, OSError)` at line 447.

### Test coverage
- **GAP-TEST-004** — `build_seed_manifest._refresh_per_tour_cost_cache()` (post-manifest cache rebuild) catches bare `Exception`, swallows all errors; no test for failure modes.
- **GAP-TEST-005** — `lint_seed_manifest.py --sha-check` drift detection has only 1 test; missing tests for partial mismatch + symlink-vs-target SHA + in-flight mutation.
- **GAP-TEST-006** — `migrate_seeds_to_new_layout.py --no-symlinks` mode tested at one level; missing re-run idempotency + crosswalk-completeness tests.
- **GAP-TEST-007** — `_seed_paths._leaf_name()` cloud+fat suffix order not pinned by test (matters for cross-platform path consistency).
- **GAP-TEST-008** — `build_seed_manifest._parse_v13_path()` parametrised over only one variant per campaign; missing malformed-path tests.
- **GAP-TEST-009** — `_config.py` inheritance cycle detection: cycle pattern (A→B→A) not tested with exact assertion; depth=8 edge case not covered.
- **GAP-TEST-010** — `sweep_parallel.py` `--seed-range` argument + Pool resumption with partial runs untested.
- **GAP-TEST-011** — `analysis/_data._load_manifest()` cache invalidation (mtime==mtime + content differs) untested.
- **GAP-TEST-012** — `submit_jobs.check_completed()` S3 prefix logic + regex pattern not exercised against any boto3 mock.

### Data integrity
- **BUG-DATA-001** — `results/seeds/q3329/q3329_degenerate_README.md` exists on disk but is **not in the manifest** AND **not in any allowlist** (`ALLOWLIST_BASENAMES`, `ALLOWLIST_PREFIXES`, `ALLOWLIST_LEGACY_PATHS`). lint_seed_manifest will flag this as a hard orphan error on next CI run. **CLOSED 2026-05-20 (commit `03bdd17`)** — `"q3329_degenerate_README.md"` added to `ALLOWLIST_BASENAMES` at `scripts/lint_seed_manifest.py:88`.
- **BUG-DATA-002** — `hash_verification.txt` (repo root) and `results/hash_verification.txt` diverge by 4 lines. Root copy missing the ad-hoc spot-check comments (AMD 9950X3D + Fresh Ubuntu VM). Unclear which is canonical.

### Docs / paper consistency
- **DRIFT-DOC-001** — Paper §Limitations text contains BOTH the new eight-dim bracket text ("eight-dimension ... 110, 120, 122, 125, 130, 140, 150, 160") AND the stale closing sentence "The β=40 cliff is confirmed at 100 seeds across all groups (n=110 through n=150)." n=160 omitted from the closing sentence. **CLOSED — pre-existing in HEAD.** Re-read of both `paper/sdbkz_paper.html` and `paper/latex/sdbkz_paper_latex.tex` shows the closing sentence already reads "...confirmed at 100 seeds across all groups (n=110 through n=150), extended at the t=1000 horizon to n=160 via the eight-dimension bracket described above." No contradiction.
- **DRIFT-DOC-002** — CHANGELOG v1.5.2 entry says "No paper §Limitations text edit; bracket sentence remains accurate at seven-dim." Reality: LaTeX + HTML already contain the eight-dim bracket (landed in commit `d79584a` outside the v1.5.2 cut). Internal contradiction. **CLOSED — pre-existing in HEAD.** `CHANGELOG.md:234-238` already carries the truthing clause: "The bracket-text update was folded in post-v1.5.2 in commit `d79584a` ... and carried forward into the v2.0.0 candidate; the original 'no paper text edit' claim reflected the v1.5.2 cut point only."

### CI / Docker
- **BUG-CI-001** — `cysignals` pinned to `==1.12.6` in Dockerfile + Dockerfile.cloud, `==1.11.4` in Dockerfile.fplll54 + Dockerfile.fplll_legacy. Numerical-core dependency split risks runtime symbol mismatches if shared code crosses image boundaries. **CLOSED 2026-05-20 (commit 3faf423)** — split is structural (fpylll 0.6.0 era stack vs main); commented in-file.
- **BUG-CI-002** — `numpy` pinned to `==2.4.4` in main/cloud, `<2.0` in fplll54/legacy. Documented reason (fpylll 0.6.0 sdist incompatible with numpy 2.x), but reproducibility-parity claim across images is violated. **CLOSED 2026-05-20 (commit 3faf423)** — range pin `numpy<2.0` upgraded to exact `numpy==1.26.4` so the sensitivity-image stack matches ADR-004's exact-pin discipline.

---

## MEDIUM findings (14)

### Python correctness
- **BUG-PY-002** — `analysis/_data.load_3x_tour_data` has a tautological condition (`if manifest_path or tour_dir is None` is always true after the preceding `if tour_dir is None: manifest_path = manifest_path or DEFAULT_MANIFEST_PATH`). **CLOSED 2026-05-20 (commit 511e61a)** — collapsed to a single branch.
- **BUG-PY-004** — `scripts/_seed_paths._require` lacks a return annotation; mypy --strict likely flags (currently shielded by `--ignore-missing-imports` + `follow_imports=silent`). **CLOSED 2026-05-20 (commit 511e61a)** — `value: object` + `-> object`.
- **BUG-PY-006** — `analysis/_data.py` uses bare `print()` at five sites instead of the centralised `log.get_logger()` convention. CLAUDE.md "Every committed script emit through scripts/log.py to pipeline.jsonl" violation.

### Data integrity
- **BUG-DATA-003 ≡ BUG-V2-002** — `scripts/verify.sh:23, 54` sets `RAW_DIR="$BASE/results/raw"` and calls `mkdir -p "$RAW_DIR"`. Directory deleted at v2.0.0; mkdir on deleted parent is benign but the dead variable is semantic debt.

### Test coverage
- **GAP-TEST-013** — `analysis/gsa_robustness.py` (full file) has NO unit tests. Computes correlation_with_dLN via scipy; NaN propagation + empty-group edge cases uncovered.
- **GAP-TEST-014** — `analysis/runtime_table.py` (entire module) has NO test file. HTML escaping + missing-manifest paths untested.
- **GAP-TEST-015** — `lint_seed_manifest._is_allowlisted` prefix/basename overlap edge cases untested.
- **GAP-TEST-016** — `q3329_verify.py` post-v2 fixup (SUMMARY_DIR redirect to `results/seeds/q3329/summary/`) untested. **CLOSED 2026-05-20 (commit 511e61a)** — static-scan test in `tests/test_v2_path_migration.py`.
- **GAP-TEST-017** — `_math_core.ln_fixed_point` + `log_clamp` at boundary dimensions (n=1, β=2, n>200) untested.
- **GAP-TEST-018** — `analysis/plots/_orchestrator.py` (figure-pipeline driver) has NO tests.

### Docs / paper
- **DRIFT-DOC-004** — `README.md:185` says "The sweep is fully resumable — it scans `results/raw/` at startup". `results/raw/` deleted; resumability walks `results/seeds/main/q97/`.
- **DRIFT-DOC-005** — Seed count framing "4,432 paper-frozen + 309 post-paper additions" misleading. Per `docs/audits/2026-05-14_zenodo_v1.5.0_contents.md`, the Zenodo v1.5.0 deposit contained 4,541 seeds at flip; the 4,432 figure is the reference-runs subset, not the published deposit.

### CI / Docker
- **BUG-CI-003** — `Dockerfile.cloud` ships scipy + pytest unpinned while main `Dockerfile` pins them. Documented reason (cloud decommissioned) but unpin contradicts the "kept in parity" comment. **FALSE ALARM 2026-05-20** — re-grep shows both files do pin `scipy==1.17.1` + `pytest==9.0.3`.
- **ISSUE-CI-005** — fplll54 + fplll_legacy Dockerfiles omit scipy + pytest entirely. Likely intentional (sensitivity-variant scope) but undocumented. **CLOSED 2026-05-20 (commit 3faf423)** — in-file comment explaining the intentional omission added to both Dockerfiles.
- **ISSUE-CI-006** — GHA action pinning inconsistent: `scorecard.yml` uses SHA pins; `build-and-verify.yml` uses semver tags. ADR-004 philosophy favours SHA pinning. **CLOSED 2026-05-20 (commit 3faf423)** — all three action `uses:` lines in build-and-verify.yml moved to SHA pins.

---

## LOW / INFORMATIONAL (20)

### Python
- **BUG-PY-005** — `analysis/_data.load_3x_tour_data` redundant `manifest_path = manifest_path or DEFAULT_MANIFEST_PATH` assignment at lines 344 + 346.
- **BUG-PY-008** — `analysis/_data._load_legacy` catches `(json.JSONDecodeError, KeyError)` but not `OSError`; inconsistent with the manifest-loader sibling.

### Test
- **GAP-TEST-019..022** — `confirm_v1_2.py` subprocess edge cases · `seed_timing.per_tour_cost_table()` cache-miss path · examples scripts error paths · `check_new_top_level_dirs.py` subprocess timeout.

### Docs
- **DRIFT-DOC-003** — false alarm on re-read (COOKBOOK §I want to add a new dimension is correct).
- **DRIFT-DOC-006** — COOKBOOK AWS Batch sections still present as active; cloud campaign decommissioned 2026-04-10. **CLOSED 2026-05-20 (commit 511e61a)** — two live-cloud sections collapsed to a single "decommissioned 2026-04-10" block.
- **DRIFT-DOC-007** — false alarm; no LaTeX/HTML inter-format drift.

### v2 migration
- **Detector gap** — `tests/test_v2_path_migration.FUNCTIONAL_RE` regex missing bare `results/convergence` (only catches `convergence_test`). No actual code hit, but the gap exists. Also: regex only covers .py files; shell scripts (verify.sh, cloud_watchdog.sh) escape detection.

### CI / Docker
- **ISSUE-CI-004** — pyproject `[tool.mypy] files` list coupling to CI step is implicit; comment refers to "pinned in .github/workflows/build-and-verify.yml" but CI doesn't pass `--select`.
- **ISSUE-CI-007** — ruff `[tool.ruff.lint] select` includes W; per-file-ignores adds E501 (E-class); cross-rule note absent.
- **ISSUE-CI-008** — dependabot correctly ignores fpylll/cysignals/numpy; no cross-reference in pyproject.toml explaining why. **CLOSED 2026-05-20 (commit 3faf423)** — in-file comment added to dependabot.yml above the ignore-list.
- **ISSUE-CI-009** — `.dockerignore` references 8 deleted legacy result directories. Benign (already excluded files don't matter) but stale. **CLOSED 2026-05-20 (commit 3faf423)** — 14 stale entries stripped; replaced with single v1.3 canonical-tree comment block.
- **ISSUE-CI-010** — scorecard.yml lacks `pull_request` trigger (likely intentional — runs weekly/on-main).
- **ISSUE-CI-011** — Neither workflow defines a `concurrency:` group; overlapping runs not cancelled. **CLOSED 2026-05-20 (commit 3faf423)** — concurrency group added to build-and-verify.yml with cancel-in-progress.

---

## Non-bugs / surfaces audited clean

- **lint_seed_manifest.ALLOWLIST_LEGACY_PATHS** — 10 pilot-seed paths match on-disk exactly ✓
- **migrate_seeds_to_new_layout.py** — post-v2 state self-consistent ✓
- **_seed_paths.py** — no orphaned helpers ✓
- **examples/output/** — example 03 writes via canonical manifest path ✓
- **seed_path_crosswalk.csv** — 4,387 entries, every `new_path` exists on disk ✓
- **analysis/figures/.sha256** — 14/14 figure hashes match committed PNGs ✓
- **paper_claims/*.json** — 18 JSONs all valid + parseable ✓
- **ADR-004 digest pin** — all 4 Dockerfiles carry `python:3.12.3-bookworm@sha256:25dee7f1...3d3c` ✓
- **snapshot.debian.org dates** — all 4 Dockerfiles use `20240614T000000Z` ✓
- **All workflows + Dockerfile COPY paths** — every source referenced exists ✓
- **`config/` allowlist** in check_new_top_level_dirs — present ✓

---

## Surfaces inspected (summary)

- 31 Python files across `scripts/`, `analysis/`, `examples/`, `tests/` (~15,000 LOC)
- 2 shell scripts (`scripts/verify.sh` 105 lines, `scripts/cloud_watchdog.sh` 260 lines)
- 4 Dockerfiles (main, cloud, fplll54, fplll_legacy)
- 2 GitHub workflows (build-and-verify, scorecard)
- 1 dependabot.yml, 1 docker-compose.yml, 1 .gitignore, 1 .dockerignore, 1 Makefile
- 11 top-level docs (README, CHANGELOG, ROADMAP, COOKBOOK, CONTRIBUTING, SECURITY, docs/*)
- 2 paper artefacts (LaTeX + HTML)
- `results/seed_manifest.json` (4,741 entries) + `results/seed_path_crosswalk.csv` (4,387 entries) + `results/hash_verification.txt` (both copies) + `analysis/figures/.sha256`
- 18 `results/paper_claims/*.json`

Total: ~22,000 lines of code + ~3,000 lines of docs + 5 JSON/CSV/SHA artefacts inspected.

---

## Next step

Prioritize. Best-practice triage filter:
1. **Tag blockers** — critical findings + items that would crash CI on next push (BUG-V2-001 cloud_watchdog, BUG-DATA-001 README orphan, BUG-PY-001 file leak in hot path).
2. **High-severity items not gating tag but high-reader-impact** — DRIFT-DOC-001/002 (paper text + CHANGELOG contradiction), DRIFT-DOC-004 (README:185 stale path), BUG-CI-001/002 (pin splits — only relevant if fplll54/legacy images get rebuilt).
3. **Medium opportunistic** — coverage gaps for surfaces where regressions would be silent (sweep_cloud, gsa_robustness, runtime_table).
4. **Low / informational** — defer to next opportunistic touch.

Recommended fix scope before v2.0.0 tag: items in tier 1 + DRIFT-DOC-001/002 + DRIFT-DOC-004. Everything else gets a "follow-up backlog entry" annotation.
