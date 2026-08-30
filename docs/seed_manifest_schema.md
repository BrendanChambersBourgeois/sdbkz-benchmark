# Seed manifest schema reference

`results/seed_manifest.json` is the single authoritative index over every seed file in the `results/seeds/<campaign>/` tree. This doc is the schema reference — if you're writing analysis code that queries the manifest, this is the field-by-field contract.

ADR-002 ([`docs/design_decisions.md`](design_decisions.md)) covers *why* the manifest exists. This doc covers *what it contains.*

## Top-level layout

Example (illustrative; `generated_utc` and per-entry timestamps drift on every rebuild and carry no scientific meaning):

```json
{
  "schema_version": 1,
  "generated_utc": "2026-04-18T12:50:44Z",
  "results_root": "results",
  "campaigns": {
    "ntru":              { "total_seeds": 6740, "tags": [],                         "q_values": [97, 113, "...", 5869] },
    "main":              { "total_seeds": 3593, "tags": ["cloud"],                 "q_values": [97] },
    "q3329":             { "total_seeds":  353, "tags": ["cloud", "degenerate", "fat", "intermediate"], "q_values": [3329] },
    "tours3x":           { "total_seeds":  500, "tags": ["3x"],                    "q_values": [97] },
    "convergence":       { "total_seeds":  340, "tags": ["test"],                  "q_values": [97] },
    "cliff500":          { "total_seeds":   20, "tags": [],                         "q_values": [97] },
    "fplll_sensitivity": { "total_seeds":   15, "tags": ["v5.4.3", "v5.4.4", "v5.4.5"], "q_values": [97] }
  },
  "seeds": [ <entry>, <entry>, ... ]
}
```

- `schema_version` — integer. Bumps only on breaking structural change. v1.3.x uses version 1.
- `generated_utc` — when `build_seed_manifest.py` last rebuilt. Drifts on every rebuild; not data-meaningful.
- `results_root` — relative path from repo root to the seed tree's parent. Always `"results"` in v1.3.x.
- `campaigns` — per-campaign rollup. `total_seeds` counts every entry in `seeds` for that campaign (lean + fat, cloud + local, across all precision buckets); `tags` is the union of every tag that appears on any entry; `q_values` is the set of distinct `q` values.
- `seeds` — flat list of entries, sorted by `(campaign, q, n, beta, seed, tags)`.

## Per-entry fields

Every entry has these fields. None are optional unless marked.

| field              | type           | notes                                                                                       |
|--------------------|----------------|---------------------------------------------------------------------------------------------|
| `campaign`         | string         | One of: `ntru`, `main`, `q3329`, `tours3x`, `convergence`, `cliff500`, `fplll_sensitivity`. |
| `path`             | string         | Repo-root-relative path. Post-v1.3.x points at `results/seeds/<campaign>/...`.               |
| `n`                | int            | Secret dimension.                                                                           |
| `beta`             | int            | BKZ block size.                                                                             |
| `seed`             | int            | Per-group seed number.                                                                     |
| `q`                | int            | Modulus. 97 (main/q97 sweeps), 3329 (ML-KEM, q3329 campaign), and ~100 distinct values 97–5869 across the `ntru` overstretched sweep. |
| `precision`        | int or null    | MPFR precision in bits. `null` for tours3x (runs at implicit 250); `ntru` uses 250 / 500 / 1000. |
| `max_tours`        | int or null    | Tour budget. `null` for tours3x (varies per subcampaign).                                   |
| `store_per_tour`   | bool or null   | Whether the seed JSON includes per-tour trajectories.                                       |
| `advantage`        | float or null  | Mean SD-BKZ advantage (nats). `null` for fat-companion entries; they carry no aggregate.    |
| `sha256`           | string         | 64-hex SHA-256 of the file at `path`.                                                       |
| `size_bytes`       | int            | Byte length.                                                                                |
| `mtime_utc`        | string         | ISO-8601 UTC mtime of the file.                                                             |
| `tags`             | list[string]   | Zero or more of: `cloud`, `fat`, `3x`, `intermediate`, `degenerate`, `test`, `v5.4.3/4/5`.  |
| `verified`         | bool           | `true` once `build_seed_manifest.py` has validated schema + advantage-finite + q-match.     |
| `verified_at_utc`  | string         | Timestamp of last verification pass.                                                        |
| `verified_by`      | string         | Tool that set `verified=true`. Always `"build_seed_manifest.py"` in v1.3.x.                 |
| `fplll_version`    | string         | Present only for `fplll_sensitivity` campaign. One of `"5.4.3"` / `"5.4.4"` / `"5.4.5"`.    |

## Campaign semantics

Campaign = **intent of the run**, not derived from parameters. A q=97 seed produced by the cliff500 sweep belongs to `cliff500`, not `main`, even though its `q` matches the main sweep.

The mapping from pre-v1.3 directory to v1.3 campaign:

| pre-v1.3 dir                       | v1.3 campaign          | tags applied                  |
|------------------------------------|------------------------|-------------------------------|
| `results/raw/`                     | `main`                 | (none)                        |
| `results/cloud/`                   | `main` or `q3329`*     | `cloud`                       |
| `results/q3329/`                   | `q3329`                | (none)                        |
| `results/q3329_n{70,80,90}_beta30/`| `q3329`                | `intermediate`                |
| `results/q3329_degenerate/`        | `q3329`                | `degenerate`                  |
| `results/cliff_500bit/`            | `cliff500`             | (none)                        |
| `results/fplll543_sensitivity/`    | `fplll_sensitivity`    | `v5.4.3` + `fplll_version`    |
| `results/fplll544_sensitivity/`    | `fplll_sensitivity`    | `v5.4.4` + `fplll_version`    |
| `results/fplll54_sensitivity/`     | `fplll_sensitivity`    | `v5.4.5` + `fplll_version`    |
| `results/3x_tours/`                | `tours3x`              | `3x` (only on `_3x_seed*` files; 10 legacy pilot seeds without `q` field are orphaned informationally) |
| `results/convergence/`             | `convergence`          | (none)                        |
| `results/convergence_test/`        | `convergence`          | `test`                        |

\* The cloud-sourced q=3329 seeds (10 AWS-Batch seeds at n=100 β=30 documented in paper §8.2) migrate from `main` to `q3329` per the "campaign = intent" principle. The `build_seed_manifest.py` walker handles this reassignment based on `q` field content, not source directory.

The `ntru` campaign has no pre-v1.3 directory — it is a **post-v1.3 native campaign** (the paper-2 NTRU dense-sublattice-discovery sweep, `forever_runner.py` + `run_campaign.py`) written directly into `results/seeds/ntru/` with no legacy migration. It is now the largest campaign in the manifest (8,728 seeds as of 2026-08-30). Its bases are Ducas–van Woerden NTRU circulants of lattice dimension `2n`; `q` sweeps the overstretched range (184 distinct moduli, 97–7177).

## New path layout (v1.3)

Per campaign:

```
ntru:              seeds/ntru/q{q}/p{precision}_mt{max_tours}/n{n:03d}_beta{beta:02d}/seed{seed:04d}.json
main:              seeds/main/q97/n{n:03d}_beta{beta:02d}/seed{seed:04d}[_cloud].json
q3329:             seeds/q3329/p{precision}_mt{max_tours}/n{n:03d}_beta{beta:02d}/seed{seed:04d}[_fat].json
cliff500:          seeds/cliff500/q97/n{n:03d}_beta{beta:02d}/seed{seed:04d}.json
fplll_sensitivity: seeds/fplll_sensitivity/v{x_y_z}/q97/n{n:03d}_beta{beta:02d}/seed{seed:04d}.json
tours3x:           seeds/tours3x/q97/n{n:03d}_beta{beta:02d}/seed{seed:04d}.json
convergence:       seeds/convergence/q97/n{n:03d}_beta{beta:02d}_mt{max_tours}/seed{seed:04d}.json
```

`_cloud` suffix appears only on `main` entries where both a local-VM copy and a cloud-Batch copy existed pre-v1.3 (205 pairs per paper §3.7 cross-env verification). Both copies preserved as distinct files at the same leaf directory under distinct filenames.

`_fat` suffix marks the per-tour trajectory companion. Fat entries have `advantage: null` and `store_per_tour: true`; their `n/beta/seed/q` match the lean sibling at the same leaf dir.

`scripts/_seed_paths.py::seed_path_for()` is the canonical path emitter for runners; `scripts/build_seed_manifest.py::_parse_v13_path()` is the canonical path parser for the walker. Any drift between the two is a bug — the manifest walker would miss new writes.

## Querying the manifest

Programmatic (preferred): use `analysis/_data.py::load_all_seeds` with kwargs:

```python
from analysis._data import load_all_seeds

# All main-sweep q=97 seeds, grouped by (n, beta):
groups = load_all_seeds(campaign="main")

# q=3329 at 1000-bit MPFR, 70 tours, grouped by (n, beta):
groups = load_all_seeds(campaign="q3329", q=3329, precision=1000, max_tours=70)

# One specific group, manifest entries only (no JSON content load):
entries = load_all_seeds(
    campaign="main", n=100, beta=30,
    load_json=False, include_unverified=False, include_fat=False,
).get((100, 30), [])
```

Ad-hoc (jq): for queries too narrow for the loader API, query the manifest directly:

```bash
# All cloud entries in the main campaign:
jq '.seeds[] | select(.campaign == "main" and (.tags | contains(["cloud"])))' \
  results/seed_manifest.json | head

# Per-campaign seed counts:
jq '.campaigns | to_entries | .[] | "\(.key): \(.value.total_seeds) seeds"' \
  results/seed_manifest.json

# Every q=3329 seed at 1000-bit, 70 tours:
jq '.seeds[] | select(.campaign == "q3329" and .precision == 1000 and .max_tours == 70)
     | {path, n, beta, seed, advantage}' \
  results/seed_manifest.json
```

## Manifest integrity

[`scripts/lint_seed_manifest.py`](../scripts/lint_seed_manifest.py) enforces three invariants on every CI push:

- **No orphans**: no file under `results/seeds/` (or a legacy path non-symlink) missing from the manifest.
- **No ghosts**: no manifest entry with an absent file.
- **No drift** (opt-in `--sha-check`): on-disk SHA-256 matches the record.

Allowlists: `seed_manifest.json` itself, the crosswalk CSV, top-level analysis rollups (`runtime_table.json`, `dGSA_summary.json`, etc.), any `summary_*.json` filename prefix, and the 10 legacy 3x_tours pilot seeds that predate the `q` field.

Exit codes: 0 clean, 1 violation, 2 manifest missing / parse error / unreadable.

## Rebuilding

```bash
python3 scripts/build_seed_manifest.py
```

- Reads every file under `results/seeds/` (native v1.3 walker) + every file under the legacy `CAMPAIGN_DIRS` list (follows symlinks and dedup via `os.path.realpath`).
- Writes `results/seed_manifest.json` atomically via `.tmp + rename`.
- ~2 seconds on 4,400+ seeds with NVMe; ~5 seconds on spinning disk.

Re-running on an unchanged tree produces a byte-identical manifest except for `generated_utc` and each entry's `verified_at_utc`. Data fields (`sha256`, `advantage`, `path`, etc.) are deterministic.

## Crosswalk CSV

`results/seed_path_crosswalk.csv` records every old-path → new-path mapping from the v1.3.0 physical migration (commit `ac52379`). 4,387 rows + header, schema:

```
old_path,new_path,sha256,campaign,n,beta,seed,is_fat,size_bytes
```

Purpose: permanent record for paper-era SHA-256 receipts (`hash_verification.txt` cites pre-v1.3 `results/raw/...` paths). When the back-compat symlinks drop at v2.0.0, the crosswalk becomes the canonical reconciler between paper-cited paths and the v2 layout.

## Not in scope here

- **Paper §3.7 cross-environment verification bytes.** See [`hash_verification.txt`](../hash_verification.txt) for the bit-identical SHA-256 table across Intel 13900K + AWS Batch + AMD 9950X3D.
- **Fat seed schema.** `*_fat.json` entries carry per-tour Rankin profile + Gram–Schmidt log-norms + RHF for both BKZ and SD-BKZ. See any `results/seeds/q3329/.../seed*_fat.json` for the layout.
- **Clamp event side-log.** `results/clamp_events.jsonl` is a separate append-only log, not indexed by the manifest. See [`pipeline_log_queries.md`](pipeline_log_queries.md) for query recipes.
