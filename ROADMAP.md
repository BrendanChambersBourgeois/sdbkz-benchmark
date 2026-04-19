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

See [`Research/CHANGELOG.md`](Research/CHANGELOG.md) for per-release details (Keep-a-Changelog format, append-only).

## Planned next

| target  | scope                                                                  | design doc                                                     |
|---------|------------------------------------------------------------------------|----------------------------------------------------------------|
| `v1.4.0` | portfolio-presentation pass: README rewrite, SECURITY.md + disclosure, CONTRIBUTING.md, ROADMAP.md, ADRs, Makefile, pipeline-log cookbook, q=3329 post-mortem. **All additive** — zero numerical drift on paper-cited files. | [`Research/backlog/2026-04-18_portfolio_presentation_plan.md`](Research/backlog/2026-04-18_portfolio_presentation_plan.md) |
| `v2.0.0` | Breaking layout change: drop legacy-path back-compat symlinks, promote crosswalk CSV as permanent record. Paper + CI + analysis argparse + sync-script coordinated edits. | [`Research/backlog/2026-04-19_v2_symlink_drop.md`](Research/backlog/2026-04-19_v2_symlink_drop.md) |

## External waits

Events gate these items. Not actionable until the trigger fires.

- **ePrint moderation**: status transitions from PENDING to PUBLISHED. Gates: fplll upstream issue filing, public-repo visibility flip, v1.4.0 release-readiness review.
- **Paper publication**: gates `docs/disclosure/fplll_gso_kahan_findings.md` timeline-section updates (upstream issue number, CVE status decision).
- **fplll upstream response**: gates `patches/README.md` status update ("upstreamed in fplll X.Y.Z" vs "patch remains necessary").

See [`Research/backlog/2026-04-19_public_flip_checklist.md`](Research/backlog/2026-04-19_public_flip_checklist.md) for the mechanical flip-day runbook and [`Research/backlog/2026-04-19_fplll_upstream_disclosure_timeline.md`](Research/backlog/2026-04-19_fplll_upstream_disclosure_timeline.md) for the upstream disclosure timeline.

## Parked with trigger conditions

Items with rough designs but no current motivator. Each has an explicit revisit trigger so future-us doesn't re-derive them.

| item                                                    | trigger                                                                                                      | doc                                                                                                  |
|---------------------------------------------------------|--------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
| Campaign config file (`config/sweep.toml`)              | ≥2 new runners per month, cross-script constant drift, or a future seed-index rev wanting per-campaign provenance | [`2026-04-18_config_file_sweep_campaigns.md`](Research/backlog/2026-04-18_config_file_sweep_campaigns.md) |
| Dockerfile `USER` directive fix                         | Opportunistic; anytime, rolls into next patch release                                                        | [`2026-04-19_dockerfile_user_directive.md`](Research/backlog/2026-04-19_dockerfile_user_directive.md) |
| Post-portfolio sweep candidates (A–F)                   | Compute window opens AND v1.4.0 shipped AND reviewer/collab asks a data-shaped question                      | [`2026-04-19_post_portfolio_sweep_candidates.md`](Research/backlog/2026-04-19_post_portfolio_sweep_candidates.md) |

Priority ranking for the sweep candidates lives in the post_portfolio doc (tier 1 = A, D; tier 2 = B, C; tier 3 = E, F).

## Project-management artefacts (existing)

These are already in the repo / Research tree. Listed here so a first-time reader can find them.

- [`Research/CHANGELOG.md`](Research/CHANGELOG.md) — Keep-a-Changelog style, per-release.
- [`Research/incidents.md`](Research/incidents.md) — 30+ operational incidents with root-cause + resolution.
- [`Research/sessions/`](Research/sessions/) — daily session journals.
- [`Research/backlog/`](Research/backlog/) — future-work docs with trigger conditions (this file links to the relevant ones).
- [`Research/audit/`](Research/audit/) — point-in-time review snapshots.

The workflow pattern throughout: every decision is logged somewhere with a date, a trigger, and a revisit condition. Nothing is "figure it out when we get there". When a trigger fires, the doc exists.

## Versioning

Loose SemVer:

- **Major** — breaking schema changes, repo rename, paper submission tag.
- **Minor** — new features, new sweep dimensions, new analysis scripts.
- **Patch** — bug fixes, infra tweaks, doc updates.

v1.x series is the paper-publication + portfolio window. v2.0.0 marks the legacy-path symlink drop (breaking layout change). v3.0.0 has no scheduled content yet.

## Contact

Questions about direction: **brendanchambersbou@gmail.com**. Open an issue for specific feature requests or paper-reproducibility questions.
