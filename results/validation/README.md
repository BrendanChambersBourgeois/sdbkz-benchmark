# results/validation/

Validation & determinism records — **NOT science seeds.** These archive the
recon/validation runs that back the ADRs (determinism gates, cross-engine
sanity checks), in a stable JSON shape so a future reader can re-derive
"was this actually checked, and what did it show?" without re-running.

Kept SEPARATE from `results/seeds/<campaign>/` by design: these must NEVER
enter `seed_manifest.json`, the paper's reproducibility seed counts, or the
SHA gates. They are auxiliary evidence, not benchmark data.

## Record schema

```json
{
  "validation": "<short-name>",      // unique id for this check
  "adr": "ADR-00N",                  // the decision it supports (or null)
  "date": "YYYY-MM-DD",
  "engine": "g6k" | "fplll" | "g6k-vs-fplll",
  "image": "<docker image used>",
  "params": { ... },                 // n, beta, seed, threads, tours, q, ...
  "result": "PASS" | "FAIL" | "INFO",
  "data": { ... },                   // the measured numbers (SHAs, profiles)
  "conclusion": "one-line verdict",
  "reproduce": "exact command to re-run"
}
```

Each file is one validation event. Append new ones; do not rewrite history.
Synced offline via `Research/ops/sync_research.sh`.
