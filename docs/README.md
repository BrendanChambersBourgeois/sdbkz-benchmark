# docs/

Reference documentation for the benchmark. Reusable capability docs live here; one-off
session journals, the incident log, and backlog notes are maintained out-of-repo.

| doc | what it covers |
|-----|----------------|
| [`design_decisions.md`](design_decisions.md) | ADRs — the *why* behind the structural decisions (code split, seed-tree migration, manifest separation, g6k determinism contract). |
| [`seed_manifest_schema.md`](seed_manifest_schema.md) | Field-by-field contract for `results/seed_manifest.json` (the fplll seed index). |
| [`ntru_metric_validity.md`](ntru_metric_validity.md) | Why the NTRU recovery metric is sound (secret-norm comparison, dim=2n circulants). |
| [`pipeline_log_queries.md`](pipeline_log_queries.md) | `jq` recipes for the `logs/pipeline.jsonl` audit stream. |
| [`incident_q3329_post_mortem.md`](incident_q3329_post_mortem.md) | Narrative of the 9-day q=3329 debugging incident that shaped the defensive-engineering policies. |
| [`disclosure/fplll_gso_kahan_findings.md`](disclosure/fplll_gso_kahan_findings.md) | The fplll Gram–Schmidt cancellation finding + Kahan mitigation (paper §8). |
| [`audits/`](audits/) | Point-in-time audit snapshots (Zenodo deposit contents, pre-tag review). Historical records — not edited after the fact. |

For contributor workflow see [`../CONTRIBUTING.md`](../CONTRIBUTING.md); for operational recipes see [`../COOKBOOK.md`](../COOKBOOK.md); for release history see [`../CHANGELOG.md`](../CHANGELOG.md).
