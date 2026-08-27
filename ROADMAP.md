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
| `v1.5.0`  | 2026-04-22 | Public flip: repo flipped private → public + Zenodo concept DOI `10.5281/zenodo.19686927` minted (per-version v1.5.0 `10.5281/zenodo.19686928`; v2.0.0 later `10.5281/zenodo.20518060`); CITATION.cff + README badges (CI / DOI / MIT / CC-BY / Python); ePrint route abandoned in favour of Zenodo as the citation anchor. |
| `v1.5.1`  | 2026-05-16 | Phase 1: Holm-Bonferroni adjusted p-values + Cliff's δ added alongside Cohen's d across the 33-cell main grid; ADR-003; `analysis/_stats_helpers.py` (88 LOC) + 19 pytest cases. Phase 2: Dockerfile base-image digest pinned to `python:3.12.3-bookworm@sha256:25dee7f1...3d3c` across all 4 Dockerfiles + apt rewritten to `snapshot.debian.org/.../20240614T000000Z/`; ADR-004; Zenodo v1.5.0 deposit content audit (`docs/audits/2026-05-14_zenodo_v1.5.0_contents.md`). Data: n=150 β=40 mt1000 (20 seeds) — material finding that the cliff is non-monotone past n=140 (cliff bottoms in the n=130–140 band; n=150 shallower by 0.36 nats). Paper §Limitations rewritten in LaTeX + HTML; PDF 31→32 pages; bracket count six→seven dimensions. Manifest 4,701 → 4,721. |
| `v1.5.2`  | 2026-05-19 | Data-only bundle: n=160 β=40 mt1000 (20 seeds, q=97, 250-bit MPFR, 1000 tours). Mean advantage at t=1000 = −1.788 nats (range [−2.225, −1.542], 0/20 win); BKZ per-tour Δ = +0.741, SD-BKZ = +0.048. Confirms the v1.5.1 "cliff bottoms in n=130–140 band" framing: bracket now eight dims +2.101 / +0.159 / −0.328 / −1.038 / −1.857 / −2.420 / −2.064 / −1.788; BKZ per-tour improvement +1.06 / +0.92 / +0.74 at n=140 / 150 / 160 (monotone softening past the bottom). Estimator extrapolation + monotone clamp from the v1.5.1→v1.5.2 cycle also folded in (predicted 80h vs observed 83.5h — within 4%). Manifest 4,721 → 4,741. No paper §Limitations text edit; bracket sentence in LaTeX + HTML remains accurate at seven-dim. |
| `v2.0.0`  | 2026-06-03 | **Breaking layout drop.** 4,387 back-compat symlinks removed across 14 dirs — canonical `results/seeds/<campaign>/…` is the sole source of truth, with `results/seed_path_crosswalk.csv` as the permanent old→new reconciler. Phase 4 CI gates (mypy / ruff / coverage / figure-parity), TOML campaign config (`config/sweep.toml` + `scripts/_config.py`), script consolidation (`run_*.py` 15 → 6, single dispatcher `run_campaign.py`; 5 one-shot verifiers → `scripts/archive/`), q=3329 §8 clamp regression gate. Zenodo v2.0.0 version DOI `10.5281/zenodo.20518060`. See CHANGELOG `[2.0.0]`. |

See [`CHANGELOG.md`](CHANGELOG.md) for per-release details (Keep-a-Changelog format, append-only).

## In flight

Post-v2.0.0 work on `main` (unreleased, no tag cut yet):

| target | scope |
|--------|-------|
| paper 2 (NTRU + cross-engine) | `paper2/` in-progress technical report: NTRU dense-sublattice-discovery (DSD) onset and a cross-engine (fplll enumeration vs G6K sieving) study. G6K wired as a second reduction engine behind a determinism-gated seam (own manifest `results/g6k_seed_manifest.json`, `lint_g6k_manifest.py`). §7 four-discrepancy reconciliation closed; core-hours corrected to recorded-time ground truth. Remaining: three §-text edits (RHF wording / bootstrap CI / R²≈0.95) + AWS §8 rerun on the corrected Kahan patch. |
| NTRU frontier campaigns | never-idle `forever_runner` filling the NTRU overstretched grid. **n=167 is a soft wall** — SD DSD-rate wanders 20–45% out to 4.97× q_fat and never crosses 50%. **n=173 is a confirmed dim-driven wall** — the matched-ratio extension (5 cells, q 5407/5843/6287/6733/7177 = 3.73–4.95× q_fat, completed 2026-08-18) held SD flat at 0–10% across 167's hot band with no 50% crossing to the 5× q_fat cap. BKZ-onset pinned at n=157 (BKZ q=2740 = 2.40× q_fat, SD q=2354 = 2.07×, lag 1.16×, 2026-08-20); the n=163 BKZ-onset extension completed 2026-08-23 (readout owed). Estimator-sized sweeps; g6k needed for n≥157 (fplll enum ceiling ~dim 300). β=50 at n=179 has produced **no crack-rate signal** — 4 completed seeds, every later seed wall-cap-killed by a cap 0.30× a healthy seed. |

## Planned next

| target   | scope                                                                  |
|----------|------------------------------------------------------------------------|
| paper 2 tag | Cut a release once §-text edits + the AWS §8 rerun land and paper2 is submission-ready. |
| g6k n≥157 | Extend the cross-engine study past the fplll enum ceiling once g6k determinism at dim ≥ 314 is characterised. |

## External waits

All v1.x-era external gates are resolved as of 2026-05-08. The Zenodo DOI is the citation anchor; ePrint moderation is no longer on the path; the upstream fplll PR was filed and closed unmerged (no further upstream action).

- ✅ **Paper publication** — Resolved 2026-04-22 via Zenodo (concept DOI `10.5281/zenodo.19686927`; v1.5.0 version DOI `10.5281/zenodo.19686928`). The disclosure doc [`docs/disclosure/fplll_gso_kahan_findings.md`](docs/disclosure/fplll_gso_kahan_findings.md) timeline now records the Zenodo mint event in place of the previous "TBD (gated on ePrint publication clearance)" row.
- ✅ **Public-repo visibility flip** — Resolved 2026-04-22.
- ✅ **fplll upstream issue filing** — Resolved 2026-05-08 via pull request [`fplll/fplll#550`](https://github.com/fplll/fplll/pull/550) ("gso: Kahan-compensated subtraction in update_gso_row"). Single-commit patch on branch `BrendanChambersBourgeois:fix/gso-kahan-cancellation`; passes 15/15 `make check`; `make check-style` clean under clang-format 18 (CI's apt version). PR body cites the Zenodo DOI for per-seed evidence. **Closed unmerged by the maintainer on 2026-05-17 ("likely AI generated"); the patch ships in-repo and paper §8 stands on its own. No further upstream action — not reopening, no fresh PR.** [`docs/disclosure/fplll_gso_kahan_findings.md`](docs/disclosure/fplll_gso_kahan_findings.md) timeline records the filing and closure events.

## Parked with trigger conditions

Items with rough designs but no current motivator. Each has an explicit revisit trigger so future-us doesn't re-derive them.

| item                                            | trigger                                                                                                          |
|-------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| Campaign config file (`config/sweep.toml`)      | ≥2 new runners per month, cross-script constant drift, or a future seed-index rev wanting per-campaign provenance |
| Post-v1.5 sweep candidates (A–F)                | Compute window opens AND reviewer/collaborator asks a data-shaped question                                       |

Priority ranking for the sweep candidates: tier 1 = A (fplll 5→10 seeds per version), D (main-sweep variance check); tier 2 = B (q=3329 n=110/120 variance), C (cliff precision at β=50); tier 3 = E (convergence to 1000 tours), F (3x tours broader at β=30). Designs maintained internally until a trigger fires. **Tier 3 item E partially executed**: n=90 / n=140 / n=150 β=30 1000-tour extensions shipped post-flip; n=130 β=40 1000-tour run since shipped. Post-v2 effort has shifted to the NTRU frontier + cross-engine study (see In flight).

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
