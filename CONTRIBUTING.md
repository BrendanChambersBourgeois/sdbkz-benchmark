# Contributing

This is primarily a research repo attached to a published paper. Most external contributors will be reviewers or collaborators reproducing results, not feature contributors. The guidance below covers both.

## Onboarding (10 min)

```bash
git clone https://github.com/BrendanChambersBourgeois/sdbkz-benchmark
cd sdbkz-benchmark
docker build -t sdbkz-benchmark:ci .                             # ~5 min
docker run --rm sdbkz-benchmark:ci bash scripts/verify.sh        # ~3 min, 5 seeds
# expect "Results: 5 passed, 0 failed out of 5", then "VERIFICATION PASSED"
```

If verify.sh passes you have a numerically-correct build. If it fails, open an issue with the output — the reference values are hardcoded in `scripts/verify.sh` and any mismatch indicates a real divergence.

If you cloned before 2026-04-25 (non-root `runner` user fix), rebuild the local image — the layered cache still runs as root and produces root-owned bind mounts. Pull, then `docker build --build-arg HOST_UID=$(id -u) --build-arg HOST_GID=$(id -g) -t sdbkz-benchmark:ci .` (omit build-args if your host UID/GID is `1000:1000`). See README Troubleshooting for the WSL / non-1000 UID path.

Host-side install (no Docker) is supported for analysis work; use the Docker image for anything that runs BKZ.

If you intend to commit anything back, install the local git hooks so the pre-commit guards run on your machine:

```bash
bash scripts/install_git_hooks.sh
```

Installs `pre-commit` (→ `scripts/check_new_top_level_dirs.py`, which refuses commits introducing un-allowlisted new top-level directories), `commit-msg` and `pre-push`. Each hook also runs an optional local guard named by `git config --local hooks.localGuard` and refuses to run if that is set but missing. The top-level-directory check guards the public-vs-internal-archive boundary. The same check runs in CI, so a missed install only delays the warning; it does not let a violation slip into `main`.

## Where to start reading

The execution path for a single seed:

```
scripts/sweep_parallel.py::worker(n, beta, seed)
  └─ scripts/sweep_parallel.py::run_single(...)
      └─ scripts/generators/lwe_kannan.py::build_lwe_kannan  # lattice generator
      └─ scripts/_bkz_core.py::run_single(...)       # canonical driver
          └─ scripts/_math_core.py::metrics_from_gso # post-tour metrics
          └─ scripts/_math_core.py::log_clamp        # defensive-clamp side-log
```

Every reduction variant (`sweep_parallel`, `sweep_cloud`, `q3329_verify`, `run_3x_extended`, `run_convergence_test`, `run_fplll54_sensitivity`) wraps the same `_bkz_core.run_single` with campaign-specific constants. The single-entry dispatcher `scripts/run_campaign.py` reads `config/sweep.toml` and routes each named campaign to one of these workhorses. Reading one wrapper teaches you the others.

The analysis path is similarly layered:

```
analysis/paper_figures.py                            # argparse CLI entry
  └─ analysis/plots/_orchestrator.py::generate_all   # figure dispatch
      └─ analysis/_data.py::load_all_seeds           # manifest query
          └─ results/seed_manifest.json              # source of truth
```

Every reader routes through `load_all_seeds` with either `campaign=...` (v1.3+ default) or legacy `*results_dirs` (still supported for back-compat).

## Branch + commit conventions

Current convention:

- Branch names: `vN.M-<topic>` for release work, `<topic>-<detail>` for fixes. Examples: `v1.2-consolidation`, `v1.3-seed-index`, `v1.3-coverage-expansion`, `fix-ci-pytest-in-docker`, `v1.4-docs`.
- Commits: one subject line under 72 characters with a conventional prefix (`feat:`, `fix:`, `docs:`, `data:`, `config:`, `ci:`, `paper2:`), no body; Co-Authored-By trailer on Claude-Code-assisted commits.
- Seed data and doc updates land as one `data:` and one `docs:` commit per day.

## Testing expectations

Before every commit:

```bash
python3 -m pytest tests/                                  # ~1.5 min
python3 scripts/lint_seed_manifest.py                     # ~0.1s
python3 -m ruff check scripts/ analysis/                  # ~0.2s
python3 -m mypy                                           # ~3s, strict on _*_core
bash scripts/verify.sh --check-only                       # ~0.5s
```

Before a commit that touches `_math_core` or `_bkz_core`:

```bash
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

The append-only event stream at `logs/pipeline.jsonl` is the answer to "what happened during this session / sweep / incident". Queryable with `jq`; see [`COOKBOOK.md`](COOKBOOK.md).

## Data discipline

The repo enforces a "never delete experimental data" rule. Seed JSONs, clamp event logs, pipeline logs, and paper-cited files are append-only by policy.

- No `rm -rf results/` or any subset thereof without an explicit backup step.
- No truncation of `logs/pipeline.jsonl` or `results/clamp_events.jsonl`.
- No rewriting committed seed JSONs. If a seed needs to be re-generated, the new version lands with a different path (e.g. under `results/seeds/<campaign>/<new_precision_bucket>/...`) and the manifest indexes both.
- Moving corrupted data is acceptable: it goes to a clearly-named `*_corrupted` location *inside* the repo (visible to reviewers), or to an offline archive kept outside the repository for non-paper-grade artifacts. **Never put that archive inside the public repo** — the audit chain stays offline (paper-grade boundary). Never `/dev/null`.

Rationale: the policy is zero-tolerance.

## Sudo / destructive actions

Scripts that invoke `sudo` or destructive commands (`docker system prune`, `git reset --hard`, `git push --force`) require explicit opt-in:

- Interactive confirmation for one-off invocations.
- An explicit `--confirm` or `--execute` flag for scripted ones (see `scripts/migrate_seeds_to_new_layout.py` for the pattern).
- Dry-run first mode is preferred; opt-in to execute-mode is required.

## Paper safety

All changes ship under a **paper-safety invariant**: zero SHA-256 drift on paper-cited files (seeds, figures, patches, paper PDF). Anything additive (docs, tests, infra) is safe. Anything that touches `_math_core`, `_bkz_core`, `_seed_paths.py` path logic, or scientific constants (`BETAS`, `NS`, `TOURS_BY_BETA`, `PRECISION`, MPFR settings) requires the full parity suite before commit and an explicit callout in the commit body.

The paper PDF, LaTeX source, and HTML mirror under `paper1/` are not edited in place; the built files land in a camera-ready commit. Direct edits to `paper1/*.pdf` / `paper1/*.html` / `paper1/latex/*.tex` from a feature branch are not an accepted workflow.

## Getting help

Contact **brendanchambersbou@gmail.com**. Paper reproducibility questions are most welcome when they cite a specific claim and seed range.

See also [`SECURITY.md`](SECURITY.md) for security-adjacent reports.
