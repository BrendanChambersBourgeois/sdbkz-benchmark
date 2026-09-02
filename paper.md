---
title: 'sdbkz-benchmark: Reproducible benchmarking of lattice-reduction algorithms via the Li–Nguyen Rankin profile'
tags:
  - Python
  - lattice reduction
  - BKZ
  - cryptanalysis
  - post-quantum cryptography
  - reproducibility
authors:
  - name: Brendan Chambers-Bourgeois
    orcid: 0009-0004-2609-0822
    affiliation: 1
affiliations:
  - name: Independent Researcher, Australia
    index: 1
date: 30 August 2026
bibliography: paper.bib
---

# Summary

Lattice basis reduction underpins the security analysis of post-quantum
cryptography: the practical hardness of schemes standardized by NIST is
estimated from how well algorithms such as BKZ [@MathProg:SchEuc94;
@AC:CheNgu11] reduce high-dimensional lattices. The dominant quality metric,
the root Hermite factor (RHF), compresses an entire reduced basis into one
scalar — and is structurally blind to differences that matter. Two algorithms
can produce numerically indistinguishable RHFs while leaving bases with
measurably different geometry.

`sdbkz-benchmark` is a containerized, seed-exact benchmark that compares
lattice-reduction algorithms at the level of the full basis profile, using the
distance to the Li–Nguyen fixed-point Rankin profile, d(LN)
[@EPRINT:LiNgu20], as the primary observable. It ships two reduction engines
behind a common seam — fplll's exact enumeration oracle [@fplll; @fpylll] and
the G6K sieve kernel [@EC:ADHKPS19] — together with campaign runners, a
SHA-256-verified seed manifest covering 13,549 fplll and 2,617 G6K runs, an
analysis package that regenerates every figure and table of the accompanying
technical report [@zenodo], and a CI pipeline that rebuilds the container and
re-derives a reference seed byte-for-byte on every commit.

# Statement of need

Concrete security estimation relies heavily on simulators and estimators
[@AC:CheNgu11; @LatticeEstimator] whose assumptions are calibrated against
comparatively few published experiments, and empirical claims about reduction
algorithms are routinely made on tens of seeds without controlled variance or
released raw data. Comparing algorithm *variants* — here, standard BKZ against
self-dual BKZ (SD-BKZ) [@EC:MicWal16; @Walter20blog] — is especially fragile:
the effects are invisible in RHF, emerge only in profile-level statistics, and
are sensitive to floating-point behaviour at cryptographically relevant moduli.

`sdbkz-benchmark` addresses this with three properties rarely found together:

1. **Profile-level observables.** Per-tour d(LN) trajectories, per-seed
   advantage statistics, and dense-sublattice-discovery (DSD) indicators are
   first-class outputs, not post-hoc scripts.
2. **Seed-exact reproducibility.** Every run is a JSON artifact indexed in a
   manifest with SHA-256, size, and verification status. The pinned Docker
   image reproduces seed files byte-identically across CPU vendors (Intel
   13900K, AMD 9950X3D) and container runtimes; a 100-seed cross-environment
   hash verification is committed.
3. **Adversarial numerical hygiene.** Defensive clamps must log the raw value
   they replace to an append-only side-channel (`results/clamp_events.jsonl`),
   a policy adopted after a silent clamp masked a genuine library bug. This
   discipline led to the isolation of a catastrophic-cancellation defect in
   fplll's Gram–Schmidt recurrence (below).

The target audience is researchers in lattice cryptanalysis and concrete
security estimation who need trustworthy empirical baselines, and developers
of reduction libraries who need regression-grade numerical test corpora.

# State of the field

fplll/fpylll [@fplll; @fpylll] and G6K [@EC:ADHKPS19] are the standard
open-source reduction engines; they provide algorithms, not benchmarks.
The lattice-estimator [@LatticeEstimator] predicts attack costs from models
rather than measurements. BKZ simulators [@AC:CheNgu11] model average-case
profile evolution but are calibrated on limited empirical data and do not
capture variant-level differences such as BKZ versus SD-BKZ. Published
experimental comparisons typically report RHF summaries on small seed counts
and rarely release per-seed artifacts. To our knowledge no existing package
offers a manifest-gated, CI-verified, multi-engine corpus of full-profile
reduction trajectories at this scale (16,032 verified seeds across LWE-Kannan
and NTRU families).

# Software design

The package is organised around one invariant: *every number in the papers is
re-derivable from a committed artifact by a fresh clone.*

- **Single write path, single read path.** All runners route output through
  `scripts/_seed_paths.py`; all analysis reads through the manifest. CI lints
  three manifest invariants (no orphan files, no ghost entries, no hash drift)
  on every push.
- **Engine separation.** fplll (enumeration) and G6K (sieving) live behind a
  determinism-gated seam with separate manifests; their hashes are never
  merged (sieving is deterministic only single-threaded, so parallelism is
  across seeds).
- **Verification as CI.** Every commit rebuilds the Docker image from
  scratch, runs the unit-test suite (mypy strict on the numerical core, 75%
  coverage floor), regenerates a paper-reference seed in the fresh container,
  and compares against committed values. A paper-figure parity gate keeps the
  technical report's figures in lockstep with the analysis code.
- **Append-only observability.** Every committed script emits structured
  events to `logs/pipeline.jsonl`; clamp events and incident postmortems are
  retained permanently. Operational failures are documented in-repo and
  converted into policies and tests rather than fixed silently.
- **Commodity-hardware scale-out.** Campaign tooling supports resumable local
  sweeps, decommissioned AWS Batch recipes, and an unattended second compute
  node (a consumer Steam Machine running the pinned image under rootless
  podman) with idempotent result pulls.

# Research impact statement

The benchmark is the artifact behind a Zenodo-published technical report
[@zenodo] whose headline methodological finding — that RHF differences below
$10^{-6}$ coexist with profile-level effect sizes up to Cohen's d = 9.6
across 4,500+ seeds — depends directly on the software's profile-level
observables. Its numerical-hygiene tooling isolated a previously unreported
catastrophic-cancellation bug in fplll's squared-form GSO recurrence that
degrades 38% of bases at q = 3329, n = 100, β = 30 even at 1000-bit MPFR
precision; the repository ships a Kahan-compensated patch (filed upstream as
fplll PR #550) and the 100-seed characterisation corpus, which is directly
usable as a regression suite by reduction-library developers. An in-progress
second report extends the corpus to circulant NTRU and cross-engine
(enumeration versus sieving) comparisons; all of its raw data is already
public in this repository. The committed corpus, crosswalk of historical
paths, and dual-licensed data (MIT code, CC-BY 4.0 data) are designed for
third-party reuse in estimator calibration and simulator validation.

# AI usage disclosure

This software, its documentation, and this manuscript were developed with
substantial assistance from Anthropic's Claude models used as an agentic
coding tool (Claude Code), under the continuous direction and review of the
author. AI assistance included code generation and refactoring, test
authoring, documentation drafting, operational tooling, and manuscript
drafting. All experimental design decisions, all acceptance or rejection of
results, and all scientific claims are the author's responsibility. No
experimental data, statistics, or figures were generated by an AI system:
every number is produced by the pinned containerized pipeline and verified by
the CI gates described above, independently of any language model.

# Acknowledgements

No financial support was received for this work.

# References
