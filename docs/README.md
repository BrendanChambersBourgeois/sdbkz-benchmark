# docs/

Reference documentation for the benchmark.

| doc | what it covers |
|-----|----------------|
| [`design_decisions.md`](design_decisions.md) | ADRs — the *why* behind the structural decisions (code split, seed-tree migration, manifest separation, g6k determinism contract). |
| [`seed_manifest_schema.md`](seed_manifest_schema.md) | Field-by-field contract for `results/seed_manifest.json` (the fplll seed index). |
| [`ntru_metric_validity.md`](ntru_metric_validity.md) | Whether d(LN) is a valid reference on NTRU bases (LN vs ZGSA; report the unsigned divergence) and the DSD validation. |
| [`images.md`](images.md) | Docker image tags: Dockerfile, build args and `make image-*` target for each. |

Contributor workflow: [`../CONTRIBUTING.md`](../CONTRIBUTING.md); release history: [`../CHANGELOG.md`](../CHANGELOG.md).
