# Security policy

## Scope

This is a **research benchmark repository**, not a deployed service or library. "Security" here means two overlapping things:

1. **Numerical-correctness bugs with cryptographic context.** Lattice reduction underwrites security estimates for post-quantum schemes (ML-KEM, Kyber, Dilithium, FrodoKEM, etc.). Bugs in reduction routines — catastrophic cancellation, incorrect Gram–Schmidt output, silent precision loss — can mis-inform parameter choice. When we find one, we treat it as a security-adjacent disclosure even when no direct exploit exists.
2. **Evidence integrity.** The paper cites SHA-256-verified seeds, bit-identical reproducibility across three compute environments, and an append-only audit chain. The CI gates and lint rules in this repo exist to keep those claims true across every commit.

If you have concerns under (1) or (2), please reach out via the contact flow below.

## Reporting

Contact: **brendanchambersbou@gmail.com** (GPG key available on request). Please include:

- A short description of the issue.
- The affected commit hash or release tag.
- A reproduction path if available (container command, seed parameters, expected vs observed output).

**Response expectations**:

- Acknowledgment within 7 days of receipt.
- Triage decision within 30 days (confirmed / can't-reproduce / out-of-scope / needs-more-info).
- No guaranteed fix timeline. This is a research repo attached to a published paper, not a deployed service with an SLA. Critical findings (numerical correctness + cryptographic context) will be prioritised; polish / doc issues may sit in backlog.

For upstream library findings (fplll, fpylll, MPFR), coordinate timing so the fix lands upstream before the public disclosure lands here. The fplll Kahan-patch finding (see below) is the reference case: it was filed upstream but the maintainer declined it, so the corrected patch now ships in-repo, local-only.

## Known findings

### fplll Gram–Schmidt cancellation at cryptographic moduli

- **Disclosure doc:** [`docs/disclosure/fplll_gso_kahan_findings.md`](docs/disclosure/fplll_gso_kahan_findings.md)
- **Patch:** [`patches/fplll_gso_kahan.patch`](patches/fplll_gso_kahan.patch) (code only) + [`patches/fplll_gso_kahan_tests.patch`](patches/fplll_gso_kahan_tests.patch) (separate regression-test diff), documented in [`patches/README.md`](patches/README.md)
- **Paper reference:** §8 of `paper1/latex/sdbkz_paper_latex.tex` (and `paper1/sdbkz_paper.html` mirror)
- **Upstream status:** filed as [fplll PR #550](https://github.com/fplll/fplll/pull/550) (2026-05-08), closed unmerged by the maintainer 2026-05-17; the corrected patch is now kept **local-only** (not resubmitted or reopened). See the disclosure doc timeline.
- **Impact summary:** At cryptographic moduli (e.g. q=3329 for ML-KEM) with `n ≥ 100`, the squared-form Gram–Schmidt recurrence in `fplll/gso_interface.cpp:147–151` suffers catastrophic cancellation, producing non-positive diagonal entries for the squared norm. Observed degeneracy rate: **38.0%** (Wilson 95% CI [29.1%, 47.8%]) at n=100 β=30 q=3329 with 1000-bit MPFR, across 100 seeds spanning 3 compute environments. The Kahan-compensated subtraction patch drops the rate to **0/55**, passes all 15 fplll regression tests (16/16 with the bundled test). `q=97` (the paper's main-sweep modulus) is unaffected at every dimension up to n=150.

## Defensive engineering

The repo embeds several policies that keep evidence integrity auditable:

### `log_clamp` side-log

Every defensive numerical clamp (substitution of a sentinel value for a non-positive Gram–Schmidt norm) writes the raw pre-substitute value to `results/clamp_events.jsonl` — timestamp, script, seed context, position, raw `get_r()` return value. The file is append-only, never truncated, and is the canonical audit trail for the §8 instability investigation.

**Why this exists:** in the 9-day q=3329 incident (narrative at [`docs/incident_q3329_post_mortem.md`](docs/incident_q3329_post_mortem.md)), an earlier clamp silently substituted a sentinel without logging the raw value. The defective `get_r()` return was invisible for 9 days while a draft §8 was being written against clamped output. Never again.

### Never-raises logging

`scripts/log.py::PipelineLogger` wraps every structured event emission in a try/except that drops the event and continues. A logging failure cannot block compute. An on-disk corruption of `logs/pipeline.jsonl` at worst loses the failing event, never the seed that was being computed.

### Append-only audit chain

- `logs/pipeline.jsonl` — every committed script emits structured events via `get_logger()`. Enforced by `scripts/lint_logging.py` as a CI gate.
- `results/clamp_events.jsonl` — defensive-clamp side-log per above.
- `results/seed_manifest.json` — every seed file indexed with SHA-256, size, mtime, verified flag. Rebuilt deterministically from the on-disk tree.

All three are append-only by policy. The repo's data-discipline rule (see [`CONTRIBUTING.md`](CONTRIBUTING.md)) forbids `rm` of experimental data without backup; no exception has ever been taken.

### `validate_seeds.py --strict --sha-check`

Per-commit CI gate. Verifies every committed seed JSON against its schema, its parsed filename, its advantage-finite invariant, and a SHA-256 spot check against hardcoded reference hashes. Any drift fails the build. A volume-preservation threshold (0.1 nats absolute, tuned against the 1,960-seed q=97 dataset) catches accumulated-rounding regressions that pass schema checks.

### `lint_seed_manifest.py`

Enforces three invariants over the manifest + tree:

- **No orphans:** every file under `results/seeds/` appears in the manifest.
- **No ghosts:** every manifest entry's `path` resolves to an existing file.
- **No drift:** (opt-in `--sha-check`) on-disk SHA-256 matches the manifest record.

CI runs the fast mode (orphan + ghost) on every push. The full `--sha-check` runs pre-tag locally.

### Cross-environment bit-identity

`results/hash_verification.txt` records SHA-256 hashes for the 100-seed (n=100, β=20) cross-environment verification. Identical across Intel 13900K (Ubuntu 24.04, MPFR 4.2.1) and AWS Batch (Debian Bookworm, MPFR 4.2.0). A cross-architecture smoke test on q=3329 n=100 β=30 seed 11 produced bit-identical output between Intel 13900K and AMD 9950X3D (different CPU vendors, different FP execution paths, different AVX / FMA behavior). Rules out microarchitecture as a failure source for numerical findings.

## Not in scope

- **Supply-chain attacks on pinned dependencies.** We pin fpylll, cysignals, numpy, matplotlib, scipy, pytest in `Dockerfile` + `pyproject.toml`. If a pinned upstream is compromised, the CI reproducibility gate (`verify.sh`) will fail rather than silently corrupt data.
- **Key escrow or cryptographic protocol design.** This is a benchmark of a specific BKZ variant against a reference algorithm; it does not propose primitives.
- **Classical ML / AI model supply chain.** No ML training or inference happens in this repo.

## Acknowledgements

Cross-architecture reproducibility verification (AMD Zen 5) courtesy of Dylan Chambers Bourgeois. Early feedback + methodology discussion from Trill White (Deakin University).
