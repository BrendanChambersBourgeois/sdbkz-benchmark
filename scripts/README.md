# scripts/

Pipeline code for the benchmark. `_`-prefixed files are internal modules (imported, not
run directly); everything else is an entry point. Every committed script emits structured
events to `logs/pipeline.jsonl` via `log.py::get_logger` (enforced by `lint_logging.py`).

## Core library (imported)

| module | role |
|--------|------|
| `_bkz_core.py` | Canonical BKZ + SD-BKZ per-seed driver (`run_single`, `dln_trajectory`). The single reduction path — all runners call it. |
| `_math_core.py` | Numerical helpers (fixed-point log, clamp semantics). |
| `_engine_backends.py` | Reduction-engine seam: `make_backend` → `fplll` \| `g6k`, behind `run_single`'s `backend` kwarg (ADR-006). |
| `generators/` | Lattice basis generators (`build_lwe_kannan`, `build_ntru` DvW circulants). |
| `_config.py` | Campaign config loader over `config/sweep.toml`. |
| `_runner_core.py`, `_seed_paths.py`, `_seed_hash.py`, `_signal_utils.py`, `log.py`, `seed_timing.py` | Runner plumbing: path emitter/parser, SHA-256, signal handling, logging, timing. |

## Running campaigns

| entry point | use |
|-------------|-----|
| `run_campaign.py` | Single dispatcher driven by `config/sweep.toml` — the canonical way to launch a sweep. |
| `forever_runner.py` | Never-idle service: works the worklist, else fills the NTRU grid. Systemd unit `config/forever-runner.service`. |
| `sweep_parallel.py`, `run_packed.py`, `run_sweep_fill.py` | Local multi-worker sweep runners. |
| `sweep_cloud.py`, `submit_jobs.py` | AWS Batch submission path. |
| `onset_driver.py` | DSD-onset bisection over `q` (`qfat(n)=0.004·n^2.484`). |
| `estimate_sweep_time.py` | Wall-time estimator — anchor-based; **size timeouts with this, never by eye**. |

## Manifests & integrity gates

| script | gate |
|--------|------|
| `build_seed_manifest.py` / `lint_seed_manifest.py` | Build + verify the fplll `results/seed_manifest.json` (no orphans / ghosts / drift). |
| `build_g6k_manifest.py` / `lint_g6k_manifest.py` | The **separate** g6k manifest (ADR-005; never merged with the fplll one). |
| `verify.sh` | Numerical-reproducibility gate (`NUM_SEEDS=1` in CI): re-runs seeds, byte-compares. |
| `verify_g6k.sh` / `g6k_probe.py` | g6k determinism gate — regenerate the reference probe in-image, exact SHA-256 match. |
| `validate_seeds.py`, `q3329_verify.py` | Per-seed schema/integrity checks. |

## Analysis & paper

`build_paper2_claims.py` (+ `_paper2_claims/`), `extract_dsd_onset.py`, `compare_xengine.py`,
`sync_paper_figures.py` — paper-2 claim ledger, DSD-onset extraction, cross-engine comparison,
and the figure-parity sync.

## Lint / CI helpers

`lint_logging.py` (central-logging coverage), `check_new_top_level_dirs.py` (INC-39 guard),
`install_git_hooks.sh`.

## Decisions

`decide.py` asks the calls that are the owner's — a ruling the work is blocked on, or a thing
only he can do — once, on a local page served on 127.0.0.1, and records the answer. Anything a
session can settle from the evidence on disk it settles itself (`resolve`), it does not ask.

    python3 scripts/decide.py add --topic worklist --q "..." --ctx "..." \
        --opt "..." --opt "..." --investigated "..." --tried "..." --why-you "..."
    python3 scripts/decide.py ask          # build, serve, open the browser, commit on Finish
    python3 scripts/decide.py ls | ledger  # what is open | what was ruled

The store is **outside the repo** — `DECIDE_HOME`, default `/mnt/hgfs/Research/decide/`
(`open.json`, append-only `ledger.jsonl`, rendered `DECISIONS.md`, built page under `out/`).
Rulings are narrative, and the public surface stays minimal. Ported 2026-09-19 from the HESTA
vault's copy at `~/Desktop/obsidian/scripts/decide/`; the two stores are wholly independent and
question ids are unique only within a store, so cite one as `topic Qnn`.

## `archive/`

Retired one-shot verifiers kept for provenance (e.g. `test_math_core_parity.py`,
`confirm_v1_2.py`) — see [`archive/README.md`](archive/README.md). Not part of the live pipeline.
