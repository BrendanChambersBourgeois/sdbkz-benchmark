# Contributing

This is primarily a research repo attached to a published paper. Most external contributors will be reviewers or collaborators reproducing results, not feature contributors. The guidance below covers both.

## Onboarding (10 min)

```bash
git clone https://github.com/BrendanChambersBourgeois/sdbkz-benchmark
cd sdbkz-benchmark
docker build -t sdbkz-benchmark:ci .                             # ~5 min
docker run --rm sdbkz-benchmark:ci bash scripts/verify.sh        # ~3 min, 5 seeds
# expect "VERIFICATION PASSED (5 passed, 0 failed)"
```

If verify.sh passes you have a numerically-correct build. If it fails, open an issue with the output — the reference values are hardcoded in `scripts/verify.sh` and any mismatch indicates a real divergence.

Host-side install (no Docker) is supported for analysis/docs work; use the Docker image for anything that runs BKZ.

## Where to start reading

The execution path for a single seed:

```
scripts/sweep_parallel.py::worker(n, beta, seed)
  └─ scripts/sweep_parallel.py::run_single(...)
      └─ scripts/_bkz_core.py::run_single(...)       # canonical driver
          └─ scripts/_math_core.py::build_lwe_kannan # lattice generator
          └─ scripts/_math_core.py::metrics_from_gso # post-tour metrics
          └─ scripts/_math_core.py::log_clamp        # defensive-clamp side-log
```

Every reduction variant (`sweep_cloud`, `q3329_verify`, `run_cliff_500bit`, `run_fplll54_sensitivity`) wraps the same `_bkz_core.run_single` with campaign-specific constants. Reading one wrapper teaches you the others.

The analysis path is similarly layered:

```
analysis/paper_figures.py                            # argparse CLI entry
  └─ analysis/plots/_orchestrator.py::generate_all   # figure dispatch
      └─ analysis/_data.py::load_all_seeds           # manifest query
          └─ results/seed_manifest.json              # source of truth
```

Every reader routes through `load_all_seeds` with either `campaign=...` (v1.3+ default) or legacy `*results_dirs` (still supported for back-compat).

## Branch + commit conventions

Observed from actual history:

- Branch names: `vN.M-<topic>` for release work, `<topic>-<detail>` for fixes. Examples: `v1.2-consolidation`, `v1.3-seed-index`, `v1.3-coverage-expansion`, `fix-ci-pytest-in-docker`, `v1.4-docs`.
- Commit subjects: conventional-ish prefix (`feat(scope)`, `fix(scope)`, `docs(scope)`, `chore(scope)`, `refactor(scope)`, `ci(scope)`), 50-70 chars.
- Commit bodies: prose paragraph explaining *why*, a short bullet list of *what*, and a **Verification** block summarising the gates that passed (pytest counts, ruff, verify.sh, lint_seed_manifest, figure SHA parity where relevant).
- Co-authored-by trailer on Claude-Code-assisted commits.

Example (`c53e08a`):

```
feat(seeds): q=3329 intermediate fill +25 seeds at 1000-bit MPFR

Overnight sweep 2026-04-18 (branch: overnight-sweep-20260418,
rename: v1.3-coverage-expansion pending). Tops up q=3329 β=30
intermediate-dimension coverage at 1000-bit MPFR, max_tours=70,
matching the paper §8 headline campaign precision:

  n=70: +5 seeds  (seeds 21-25),  3.09h wall,  22-worker pool
  n=80: +10 seeds (seeds 21-30),  6.93h wall,   8-worker pool
  n=90: +10 seeds (seeds 21-30),  8.72h wall,   8-worker pool
  ─────────────────────────────────
  total +25 seeds, ~18.7h cumulative worker-wall

Per-seed advantages all positive (+0.17 to +0.98 nats...)
...
Manifest: 4387 → 4412 entries (forward-compat walker shipped in
prior commit 2b5365c). lint_seed_manifest --sha-check: 0 orphan /
0 ghost / 0 drift.
...
```

## Testing expectations

Before every commit:

```bash
python3 -m pytest tests/                                  # ~1s, 96 tests
python3 scripts/lint_seed_manifest.py                     # ~0.1s
python3 -m ruff check scripts/ analysis/                  # ~0.2s
bash scripts/verify.sh --check-only                       # ~0.5s
```

Before a commit that touches `_math_core` or `_bkz_core`:

```bash
python3 scripts/test_math_core_parity.py                  # 576 bit-identity comparisons
bash scripts/verify.sh                                    # regenerates 5 seeds (~3min)
```

Before a commit that touches `analysis/` (figures / tables / stats):

```bash
# Regenerate and compare figure SHA-256 against a pre-edit baseline
mkdir -p /tmp/figs_pre /tmp/figs_post
# (stash changes; run; sha256sum; pop; run; diff)
```

Figure SHA-256 byte-identity is the hard invariant for anything analysis-side. A byte-difference means the dataset or the rendering drifted — either is worth investigating before the commit lands.

## Logging

Every committed script must emit structured events through `scripts/log.py::get_logger`. `scripts/lint_logging.py` scans `scripts/` + `analysis/` on every CI run and fails if any entry-point file uses bare `print()` without a matching PIPELINE emit.

The append-only event stream at `logs/pipeline.jsonl` is the answer to "what happened during this session / sweep / incident". Queryable with `jq`; see [`COOKBOOK.md`](COOKBOOK.md) (when the cookbook ships — Phase 7).

## Data discipline

The repo enforces a "never delete experimental data" rule. Seed JSONs, clamp event logs, pipeline logs, and paper-cited files are append-only by policy.

- No `rm -rf results/` or any subset thereof without an explicit backup step.
- No truncation of `logs/pipeline.jsonl` or `results/clamp_events.jsonl`.
- No rewriting committed seed JSONs. If a seed needs to be re-generated, the new version lands with a different path (e.g. under `results/seeds/<campaign>/<new_precision_bucket>/...`) and the manifest indexes both.
- Moving corrupted data is acceptable: it goes to a clearly-named `*_corrupted` or `_archives/` location, never `/dev/null`.

Rationale: the policy is zero-tolerance. The one time we bent it (an early incident) produced a 9-day debugging loss. Narrative at [`docs/incident_q3329_post_mortem.md`](docs/incident_q3329_post_mortem.md).

## Sudo / destructive actions

Scripts that invoke `sudo` or destructive commands (`docker system prune`, `git reset --hard`, `git push --force`) require explicit opt-in:

- Interactive confirmation for one-off invocations.
- An explicit `--confirm` or `--execute` flag for scripted ones (see `scripts/migrate_seeds_to_new_layout.py` for the pattern).
- Dry-run first mode is preferred; opt-in to execute-mode is required.

## Paper safety

All changes ship under a **paper-safety invariant**: zero SHA-256 drift on paper-cited files (seeds, figures, patches, paper PDF). Anything additive (docs, tests, infra) is safe. Anything that touches `_math_core`, `_bkz_core`, `_seed_paths.py` path logic, or scientific constants (`BETAS`, `NS`, `TOURS_BY_BETA`, `PRECISION`, MPFR settings) requires the full parity suite before commit and an explicit callout in the commit body.

The paper PDF, LaTeX source, and HTML mirror under `paper/` are edited exclusively through `paper_findings.md` (external to the repo) plus a camera-ready session. Direct edits to `paper/*.pdf` / `paper/*.html` / `paper/latex/*.tex` from a feature branch are not an accepted workflow.

## Getting help

Contact **brendanchambersbou@gmail.com**. Paper reproducibility questions are most welcome when they cite a specific claim and seed range.

See also [`SECURITY.md`](SECURITY.md) for security-adjacent reports.
