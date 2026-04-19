# Roadmap

A visible project-management artefact. Tracks what's shipped, what's next, what's parked with explicit trigger conditions, and what's gated on external events.

## Shipped

| tag       | date       | summary                                                                            |
|-----------|------------|------------------------------------------------------------------------------------|
| `v1.0`    | 2026-04-14 | Initial public release: paper, 4,300 seeds, Docker reproducibility chain, CI gates |
| `v1.1.0`  | 2026-04-18 | LaTeX paper port (iacrj), Kahan fplll patch shipped, cliff 500-bit + fplll 5.4.x sensitivity, §3.7 + §7.4 paper edits |
| `v1.2.0`  | 2026-04-18 | Code consolidation: `_math_core` + `_bkz_core` split, 30-seed cross-path bit-identity verification, dashboard removal |
| `v1.3.0`  | 2026-04-18 | Seed consolidation: `results/seeds/<campaign>/` tree with verify-gated `seed_manifest.json`, physical migration of 4,387 seeds, `lint_seed_manifest` CI gate, 14/14 figure SHA-256 preserved |
| `v1.3.1`  | 2026-04-19 | q=3329 intermediate fill (+25 seeds at 1000-bit MPFR across n∈{70,80,90} seeds 21-30) + manifest walker forward-compat fix |

See [`CHANGELOG.md`](CHANGELOG.md) for per-release details (Keep-a-Changelog format, append-only).

## Planned next

| target   | scope                                                                  |
|----------|------------------------------------------------------------------------|
| `v1.4.0` | Reader-facing documentation pass: README rewrite, SECURITY.md + disclosure, CONTRIBUTING.md, ROADMAP.md, ADRs, Makefile, pipeline-log cookbook, q=3329 post-mortem. **All additive** — zero numerical drift on paper-cited files. |
| `v2.0.0` | Breaking layout change: drop legacy-path back-compat symlinks, promote `results/seed_path_crosswalk.csv` as permanent record. Coordinated edits across paper §9, CI `validate_seeds` step, `analysis/` argparse defaults, runner path shims. |

## External waits

Events gate these items. Not actionable until the trigger fires.

- **ePrint moderation**: status transitions from PENDING to PUBLISHED. Gates: fplll upstream issue filing, public-repo visibility flip, v1.4.0 release-readiness review.
- **Paper publication**: gates [`docs/disclosure/fplll_gso_kahan_findings.md`](docs/disclosure/fplll_gso_kahan_findings.md) timeline-section updates (upstream issue number, CVE-status decision).
- **fplll upstream response**: gates [`patches/README.md`](patches/README.md) status update ("upstreamed in fplll X.Y.Z" vs "patch remains necessary").

Public-flip runbook and upstream disclosure timeline are maintained internally; the concrete triggers above are the signal to promote them into in-repo documentation.

## Parked with trigger conditions

Items with rough designs but no current motivator. Each has an explicit revisit trigger so future-us doesn't re-derive them.

| item                                            | trigger                                                                                                          |
|-------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| Campaign config file (`config/sweep.toml`)      | ≥2 new runners per month, cross-script constant drift, or a future seed-index rev wanting per-campaign provenance |
| Dockerfile `USER` directive fix                 | Opportunistic; anytime, rolls into next patch release                                                            |
| Post-v1.4 sweep candidates (A–F)                | Compute window opens AND v1.4.0 shipped AND reviewer/collab asks a data-shaped question                          |

Priority ranking for the sweep candidates: tier 1 = A (fplll 5→10 seeds per version), D (main-sweep variance check); tier 2 = B (q=3329 n=110/120 variance), C (cliff precision at β=50); tier 3 = E (convergence to 1000 tours), F (3x tours broader at β=30). Designs maintained internally until a trigger fires.

## Project-management artefacts

In-repo:

- [`CHANGELOG.md`](CHANGELOG.md) — per-release details (Keep-a-Changelog).
- [`docs/design_decisions.md`](docs/design_decisions.md) — two ADR sections on the v1.2 / v1.3 structural decisions.
- [`docs/incident_q3329_post_mortem.md`](docs/incident_q3329_post_mortem.md) — narrative of the 9-day debugging incident that shaped the defensive-engineering policies.
- [`docs/pipeline_log_queries.md`](docs/pipeline_log_queries.md) — jq recipes for investigating the audit chain.
- [`docs/seed_manifest_schema.md`](docs/seed_manifest_schema.md) — field reference for `results/seed_manifest.json`.

Working artefacts maintained internally (session journals, incident log, backlog docs, audit snapshots) feed this roadmap + the in-repo docs; they are not themselves published.

The workflow pattern throughout: every decision is logged somewhere with a date, a trigger, and a revisit condition. Nothing is "figure it out when we get there". When a trigger fires, the doc exists.

## Versioning

Loose SemVer:

- **Major** — breaking schema changes, repo rename, paper submission tag.
- **Minor** — new features, new sweep dimensions, new analysis scripts.
- **Patch** — bug fixes, infra tweaks, doc updates.

v1.x series is the paper-publication window: v1.0–v1.3.x for the campaign itself, v1.4.x for reader-facing docs. v2.0.0 marks the legacy-path symlink drop (breaking layout change). v3.0.0 has no scheduled content yet.

## Contact

Questions about direction: **brendanchambersbou@gmail.com**. Open an issue for specific feature requests or paper-reproducibility questions.
