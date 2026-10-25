# Contributing

Most readers reproduce results rather than add features. Build and verify first:

```bash
docker build -t sdbkz-benchmark:ci .
docker run --rm sdbkz-benchmark:ci bash scripts/verify.sh   # 5 seeds, ~3 min, ends "VERIFICATION PASSED"
```

A failing `verify.sh` is a real numerical divergence; open an issue with the output.

## Code map

One seed runs through `scripts/run_campaign.py` (reads `config/sweep.toml`) → a runner (`sweep_parallel.py`, `q3329_verify.py`, the NTRU worker) → `scripts/_bkz_core.py::run_single` → `scripts/_math_core.py` for the metrics. Figures run through `analysis/paper_figures.py` → `analysis/_data.py::load_all_seeds` → `results/seed_manifest.json`.

## Before a commit

```bash
bash scripts/install_git_hooks.sh      # once per clone: pre-commit, commit-msg, pre-push
make verify                            # ruff, mypy, pytest, lint_logging, lint_seed_manifest, verify.sh
```

Commits: one subject line under 72 characters with a conventional prefix (`feat:`, `fix:`, `docs:`, `data:`, `config:`, `ci:`, `paper2:`), no body. Seed data and docs land as one `data:` and one `docs:` commit per push.

## Invariants

- Paper-cited files (seeds, figures, patches, paper PDFs) never change SHA-256. A change to `_math_core`, `_bkz_core`, `_seed_paths.py` or a scientific constant needs the parity suite (`make verify`, figure SHA comparison) before it lands.
- Experimental data is never deleted. A bad seed moves to a `*_corrupted` directory in the repo or to an offline archive; a regenerated seed lands at a new path and the manifest indexes both.
- Every committed script logs through `scripts/log.py::get_logger`; `scripts/lint_logging.py` enforces it in CI. `logs/pipeline.jsonl` and `results/clamp_events.jsonl` are append-only.
- Defensive clamps log the raw value before substituting a sentinel.
- `paper1/` is not edited in place; built files land in a camera-ready commit.

Contact: brendanchambersbou@gmail.com. See `SECURITY.md` for correctness reports with cryptographic context.
