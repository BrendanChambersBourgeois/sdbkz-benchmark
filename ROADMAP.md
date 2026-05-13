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
| `v1.4.0`  | 2026-04-19 | Reader-facing documentation pass: SECURITY.md + disclosure docs, CONTRIBUTING.md, ROADMAP.md, ADRs, Makefile, pipeline-log cookbook, q=3329 post-mortem. All additive — zero numerical drift on paper-cited files. |
| `v1.4.1`  | 2026-04-21 | Pre-flip polish: `pyproject.toml` version pin sync, README seed-count refresh, fresh-VM reproducibility incident docs (INC-33..38), Dockerfile self-containment + non-root USER directive prep, log-cleanup follow-through (`progress.log` retired, `pipeline.jsonl` consolidation). |
| `v1.5.0`  | 2026-04-22 | Public flip: repo flipped private → public + Zenodo concept DOI `10.5281/zenodo.19686928` minted (per-version v1.5.0 `10.5281/zenodo.19686929`); CITATION.cff + README badges (CI / DOI / MIT / CC-BY / Python); ePrint route abandoned in favour of Zenodo as the citation anchor. |

See [`CHANGELOG.md`](CHANGELOG.md) for per-release details (Keep-a-Changelog format, append-only).

## In flight

| target | scope |
|--------|-------|
| Unreleased | Post-flip operational hardening: dependabot config (pip + docker + GHA), OpenSSF Scorecard workflow, pre-commit guard for new top-level directories (INC-39 follow-up), self-contained Docker image (analysis + tests + paper-cited results JSONs ship with image), non-root `runner` user via `HOST_UID`/`HOST_GID` build-args (Incident #32 closed), GHA actions bumped to Node 24 majors, paper-figure parity gate (`paper/fig*.png` ↔ `analysis/figures/`), seed_timing wall-time estimator (lib + CLI + cache + dispatcher hook). Cumulative since `v1.5.0`. Tag will be `v1.5.1` when the next bundle (β=30 mt1000 trio + β=40 mt1000 first run) lands. |

## Planned next

| target   | scope                                                                  |
|----------|------------------------------------------------------------------------|
| `v1.5.1` | Convergence trio: n=90 / n=140 / n=150 β=30 mt1000 (all shipped); n=130 β=40 mt1000 (in-flight, completes ~2026-04-26 to -28). Paper §Limitations rework batched with these data points. |
| `v2.0.0` | Breaking layout change: drop legacy-path back-compat symlinks, promote `results/seed_path_crosswalk.csv` as permanent record. Coordinated edits across paper §9, CI `validate_seeds` step, `analysis/` argparse defaults, runner path shims, examples + COOKBOOK rewrites. See [`Research/backlog/2026-04-19_v2_symlink_drop.md`](https://github.com/BrendanChambersBourgeois/sdbkz-benchmark) (offline) for the 14-step plan. |

## External waits

All v1.x-era external gates are resolved as of 2026-05-08. The Zenodo DOI is the citation anchor; ePrint moderation is no longer on the path; upstream fplll PR is filed.

- ✅ **Paper publication** — Resolved 2026-04-22 via Zenodo DOI `10.5281/zenodo.19686928`. The disclosure doc [`docs/disclosure/fplll_gso_kahan_findings.md`](docs/disclosure/fplll_gso_kahan_findings.md) timeline now records the Zenodo mint event in place of the previous "TBD (gated on ePrint publication clearance)" row.
- ✅ **Public-repo visibility flip** — Resolved 2026-04-22.
- ✅ **fplll upstream issue filing** — Resolved 2026-05-08 via pull request [`fplll/fplll#550`](https://github.com/fplll/fplll/pull/550) ("gso: Kahan-compensated subtraction in update_gso_row"). Single-commit patch on branch `BrendanChambersBourgeois:fix/gso-kahan-cancellation`; passes 15/15 `make check`; `make check-style` clean under clang-format 18 (CI's apt version). PR body cites the Zenodo DOI for per-seed evidence. Maintainer-side review cadence is theirs to set; no follow-up nudges planned from our side. [`docs/disclosure/fplll_gso_kahan_findings.md`](docs/disclosure/fplll_gso_kahan_findings.md) timeline records the filing event.

## Parked with trigger conditions

Items with rough designs but no current motivator. Each has an explicit revisit trigger so future-us doesn't re-derive them.

| item                                            | trigger                                                                                                          |
|-------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| Campaign config file (`config/sweep.toml`)      | ≥2 new runners per month, cross-script constant drift, or a future seed-index rev wanting per-campaign provenance |
| Post-v1.5 sweep candidates (A–F)                | Compute window opens AND reviewer/collaborator asks a data-shaped question                                       |

Priority ranking for the sweep candidates: tier 1 = A (fplll 5→10 seeds per version), D (main-sweep variance check); tier 2 = B (q=3329 n=110/120 variance), C (cliff precision at β=50); tier 3 = E (convergence to 1000 tours), F (3x tours broader at β=30). Designs maintained internally until a trigger fires. **Tier 3 item E partially executed**: n=90 / n=140 / n=150 β=30 1000-tour extensions shipped post-flip; n=130 β=40 1000-tour run currently in flight.

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

v1.x series is the paper-publication window: v1.0–v1.3.x for the campaign itself, v1.4.x for reader-facing docs, v1.5.x for the public flip + Zenodo DOI + post-flip operational hardening + follow-up convergence data. v2.0.0 marks the legacy-path symlink drop (breaking layout change). v3.0.0 has no scheduled content yet.

## Contact

Questions about direction: **brendanchambersbou@gmail.com**. Open an issue for specific feature requests or paper-reproducibility questions.
