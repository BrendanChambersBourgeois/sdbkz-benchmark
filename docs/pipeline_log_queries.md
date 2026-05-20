# Pipeline log query cookbook

`logs/pipeline.jsonl` is the append-only structured event stream from every committed script in this repo. It's queryable with `jq`. This doc is a cookbook of investigations we've actually run against it — recruiters / reviewers / collaborators should be able to copy a recipe and adapt.

If you're reading this for cyber / incident-response signal: the point is that the repo has a single authoritative event stream that lets you reconstruct what happened during any session, sweep, or incident, and the queries below demonstrate the patterns.

## Schema

Every line is a single JSON object. Common fields:

- `ts` — ISO-8601 UTC timestamp
- `level` — `INF` / `WRN` / `ERR`
- `script` — which committed script emitted (`sweep_parallel`, `q3329_verify`, `build_seed_manifest`, `lint_seed_manifest`, ...)
- `msg` — short human-readable message (verb phrase, not prose)
- `cat` — category tag: `sweep` / `manifest` / `migrate` / `audit` / `validation`
- Event-specific fields: `n`, `beta`, `seed`, `q`, `precision`, `elapsed_s`, `seeds`, `campaigns`, `orphan`, `ghost`, `drift`, ...

Not every record has every field. `jq select()` patterns below filter tolerantly.

A correlation ID (`run_id`) is emitted per sweep invocation; workers + any subprocess descendants inherit it via `BKZ_RUN_ID` env.

## Recipes

### How many seeds completed per sweep session today?

```bash
jq -r --arg d "$(date -u +%Y-%m-%d)" '
  select(.script == "sweep_parallel" and .msg == "worker completed" and (.ts | startswith($d)))
  | "\(.n) \(.beta) \(.seed)"
' logs/pipeline.jsonl | wc -l
```

### Which run_id emitted the cliff-500-bit events?

The pre-v2.0.0 `run_cliff_500bit.py` launcher was retired in favour of
`run_campaign.py --campaign cliff500`; historical log entries (the
ones the original cliff-500-bit run produced) still carry
`script: "run_cliff_500bit"`. New invocations carry
`script: "run_campaign"` with `ctx.campaign == "cliff500"`. Query both:

```bash
jq -r 'select(.script == "run_cliff_500bit"
              or (.script == "run_campaign" and .ctx.campaign == "cliff500")
       ) | .run_id' logs/pipeline.jsonl | sort -u
```

### How many clamp events at q=3329 across the whole campaign?

Clamp events land in a dedicated append-only side-log, not pipeline.jsonl. Use:

```bash
jq -r 'select(.raw_value <= 0) | .raw_value' results/clamp_events.jsonl \
  | wc -l

# Breakdown by script:
jq -r 'select(.raw_value <= 0) | .script_name' results/clamp_events.jsonl \
  | sort | uniq -c | sort -rn
```

### Longest seed wall time in the dataset?

```bash
jq -r '
  select(.script == "sweep_parallel" and .msg == "worker completed" and (.elapsed_s != null))
  | "\(.elapsed_s | round) \(.n) \(.beta) \(.seed)"
' logs/pipeline.jsonl | sort -n | tail -5
```

### All lint_seed_manifest runs, with their orphan/ghost/drift counts

```bash
jq -c '
  select(.script == "lint_seed_manifest" and .msg == "lint done")
  | {ts, orphan, ghost, drift, entries, elapsed_s}
' logs/pipeline.jsonl
```

Use this to diff the manifest state over time. A change in the ghost count between runs means a file moved; a non-zero drift means on-disk bytes changed under a manifest entry.

### Manifest build history — when did it last run clean?

```bash
jq -c '
  select(.script == "build_seed_manifest" and .msg == "manifest build done")
  | {ts, seeds, rejects, campaigns, elapsed_s}
' logs/pipeline.jsonl | tail -10
```

### Every `WARN get_r <= 0` event with context

The live log embeds these as `WARNING:` lines; the structured record lives in `results/clamp_events.jsonl`:

```bash
jq -c '
  select(.raw_value != null and .raw_value <= 0)
  | {ts, script: .script_name, ctx, position, raw_value}
' results/clamp_events.jsonl | head
```

Paper §8 / the q=3329 post-mortem cite this as the canonical failure fingerprint — every degenerate seed hits `raw_value = -something-finite`, and the substituted sentinel is `1e-300` giving `0.5 * log(1e-300) ≈ -345.39`.

### Did any migrate_seeds --execute touch a file outside the plan?

```bash
jq -c '
  select(.script == "migrate_seeds" and .cat == "migrate")
  | {ts, msg, mode, total_moves, moved, symlinked, problems}
' logs/pipeline.jsonl
```

Pair with `results/seed_path_crosswalk.csv` to reconstruct every old→new mapping, SHA-256-indexed. The crosswalk CSV is the permanent record the paper §9 will eventually point at when the back-compat symlinks drop at v2.0.0.

### Cross-session correlation: what was the VM doing during the 9-day q=3329 incident?

Filter by date range:

```bash
jq -c '
  select((.ts >= "2026-04-02T00:00:00") and (.ts < "2026-04-11T00:00:00"))
  | select(.script == "q3329_verify" or .script == "investigate_q3329_get_r")
  | {ts, script, msg, n, beta, seed}
' logs/pipeline.jsonl
```

This reconstructs the 9-day investigation timeline documented in `docs/incident_q3329_post_mortem.md`. Pair with `results/clamp_events.jsonl` filtered to the same window for the raw `get_r()` returns.

### Every test run, pass/fail, entry count

```bash
jq -c '
  select(.script == "pytest" or (.cat == "validation" and .msg | test("test|parity|check")))
  | {ts, script, msg}
' logs/pipeline.jsonl
```

(pytest doesn't emit into pipeline.jsonl directly; CI logs + local `pytest tests/` stdout are the authority. The recipe above covers validation / parity / lint passes that do emit.)

## Building new queries

The emit pattern is consistent across every committed script — a `PIPELINE.info(<msg>, cat=<category>, **kwargs)` call at each significant event. Read a script's top to find its category tag, grep for `PIPELINE.` calls to enumerate its events, then combine the category + message filters.

If the answer to "what happened during this run?" requires grepping text logs, the script should be emitting a structured event instead. `scripts/lint_logging.py` enforces the broad rule (every entry-point script must import `get_logger`); adding new events is a one-line change.

## Not in scope here

- **Real-time streaming.** pipeline.jsonl is append-only; `tail -F | jq ...` works for live monitoring but this doc is about after-the-fact investigation.
- **Event deletion / retention.** Zero retention policy. The file grows forever, never truncates. At current emit rates (~300 events per sweep, ~10 sweeps per campaign) total size stays under 10 MB for the paper-era campaign. No rotation needed.
- **Cross-machine correlation.** Each machine has its own pipeline.jsonl; no distributed log aggregation. For the 9-day q=3329 incident, the two machines' logs were compared manually against `hash_verification.txt` and `clamp_events.jsonl`. Cross-machine queries would need merge + dedup on timestamp + `run_id`.
