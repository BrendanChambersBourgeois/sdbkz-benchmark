# Incident post-mortem: the 9-day q=3329 investigation

This is the narrative version of the investigation that led to the `fplll` Kahan-patch finding ([`docs/disclosure/fplll_gso_kahan_findings.md`](disclosure/fplll_gso_kahan_findings.md)). It is written as a post-mortem, not a disclosure — the disclosure doc focuses on "what the bug is and how to fix it"; this doc focuses on "how we figured it out, and what we changed in the repo to stop wasting 9 days on the next one."

If you're reading this from a cyber / incident-response angle: the interesting parts are the diagnostic chain, the failure of rate-based metrics, and the policy changes that came out (mandatory raw-value logging, append-only audit chain, manifest-gated lint).

---

## TL;DR

A defensive clamp in a verification script silently substituted a sentinel value for a non-positive `get_r()` return from fplll at q=3329, n=100, β=30, 1000-bit MPFR. The clamp fired on ~38% of seeds, but neither the clamp event nor the raw pre-clamp value was logged. The draft paper §8 was written against the clamped output for 9 days (absolute dates: 2026-04-02 → 2026-04-10). The root cause was not detected until someone asked "what does `get_r()` actually return?" — a question that took 5 minutes to answer via a standalone reproducer and turned a rate-based statistical investigation into an algorithmic one.

The fix is a 30-line Kahan-compensated subtraction in `fplll/gso_interface.cpp`. The policy fallout is:

1. Every defensive clamp logs the raw pre-substitute value to an append-only side-log before substituting.
2. The side-log (`results/clamp_events.jsonl`) is never truncated.
3. A `lint_seed_manifest` CI gate catches orphan files and on-disk SHA-256 drift so the next surprise can't hide for 9 days.

The incident cost ~9 days of debugging time (absolute dates: 2026-04-02 → 2026-04-10), prompted a substantive Section 8 rewrite, and directly shaped the defensive-engineering sections of [`SECURITY.md`](../SECURITY.md).

---

## Day 0: the symptom

(Day 0 = 2026-04-02; Day 9 = 2026-04-10. Numbered headings below stay relative for narrative flow; absolute mapping is one-to-one from this anchor.)

The paper's main sweep runs at q=97 (a small non-cryptographic modulus, chosen to keep per-seed runtime minutes rather than days). To strengthen generalisability, a 20-seed verification run at q=3329 (the ML-KEM modulus) was added at n=50, β=30. Result: 100% SD-BKZ win rate, mean advantage +0.437 nats — consistent with q=97 behaviour. Paper §3 gained a one-liner pointing at the q=3329 result as evidence that the main finding is not a small-modulus artifact.

Scaling the q=3329 verification to n=100 was the natural next step. It would give a full paper §8 section on SD-BKZ at cryptographic moduli.

The n=100 run produced something unexpected: a bimodal advantage distribution. Roughly 60% of seeds fell into the "clean" +0.5 nat cluster we'd expect; the other 40% scattered across ±170 nats — positive and negative, far outside any plausible physical d(LN) advantage.

## Day 0–2: the rate-based investigation

First hypothesis: this is a statistical artefact of BKZ's non-determinism. Run more seeds, see if the bimodality sharpens or smooths.

Ran 100 seeds. Bimodality held. 38 of 100 seeds (38.0%, Wilson 95% CI [29.1%, 47.8%]) were in the anomalous cluster. Spike was sharp enough that the Intel 13900K (VM) and AMD 9950X3D (Dylan's machine) results matched to within sampling noise: 38.2% vs 37.8%. The second machine brought 45 more seeds; the combined dataset was enormous for a statistics problem but the bimodality was too clean to be sampling variance.

Second hypothesis: microarchitecture-specific FP behaviour. Different CPUs, different AVX / FMA behaviour, one of them produces slightly different `get_r()` values. Ran a bit-identity spot-check: same seed (seed 11), same parameters, both machines. Output JSONs were **byte-identical**. Rules out microarchitecture entirely.

Third hypothesis: a race condition in the multiprocessing pool. Ran the same seed single-threaded. Anomaly reproduced. Rules out parallelism.

Fourth hypothesis: non-deterministic BKZ (auto-abort, tour re-ordering). Checked `FPLLL.set_random_seed()` behaviour; checked for any global state in fpylll that could leak between pool workers. Nothing.

At this point ~5 days had elapsed. The paper draft's §8 was being written assuming the 38% was a real finding about SD-BKZ instability — "at cryptographic moduli, SD-BKZ degenerates in some fraction of seeds" — with Wilson CIs and Cohen's d tables to back it up.

## Day 6: the meta-lesson (that took 3 more days to apply)

A reviewer (self, re-reading the draft) asked the obvious-in-retrospect question: *what are the actual `get_r()` values in a degenerate seed?* The §8 text was quoting `d(LN)` spikes of ±170 nats. `d(LN)` is a derived metric — it's a mean over absolute differences to a theoretical profile. The spikes were 170 nats because the Gram–Schmidt log-norms were touching the precision floor.

The raw output of `M.get_r(i, i)` for a degenerate seed's problem position was `0.5 * log(1e-300) ≈ -345.39`. A mathematically-impossible value for `log(‖b*_k‖²)`.

This is the meta-lesson: **when numbers look unusual, check raw values, not derived metrics.** Aggregates (rates, CIs, Wilson intervals, Cohen's d) lose the smoking-gun information. A single direct call to the underlying API beats another aggregate computation. 9 days earlier, a one-line print statement would have answered the question.

But "the raw value is the precision-floor clamp" was not the final answer. The clamp was *added* at some point as defensive code. What was the value `get_r()` actually returned *before* the clamp substituted?

## Day 7: the direct capture

Wrote a standalone reproducer: `analysis/investigate_q3329_get_r.py`. Ran cloud seed 1 tour-by-tour with MPFR=1000 bits, captured `M.get_r(i, i)` for every `(tour, i)` pair, wrote to a JSON log.

First interesting event: at tour 30, position 293, `M.get_r(293, 293) = -1.2805632996020577`. A finite, non-zero, non-NaN, non-Inf, non-positive value. For a squared Gram–Schmidt norm. Mathematically impossible.

That's when the investigation changed from "SD-BKZ instability at q=3329" to "fplll returns negative squared norms at q=3329".

Second interesting observation, from running the reproducer a second time on the same input: the sequence of negative values was **different**. Same seed, same lattice, same MPFR precision, same random-seed injection — run 1 hit the collapse at tour 30, run 2 made it 40 tours cleanly. A stable physical norm doesn't flip sign across runs. The value was teetering on zero, and FP rounding was deciding which side it fell on.

That's catastrophic cancellation.

## Day 8: the root cause

Opened `fplll/gso_interface.cpp` at `update_gso_row`. Found the offending loop at lines 147–151. Verified by reading: no compensation, no reorthogonalisation trigger, no sign check on the result. The squared-form Cholesky-style recurrence — `r(i,i) = ‖b_i‖² − Σ μ² · ‖b*_k‖²` — is computed as a straight in-place subtraction. For near-degenerate input (which is exactly what BKZ drives lattices towards at high dimension + cryptographic modulus), the two operands approach each other in magnitude, cancel, and leave a residual whose sign is noise.

Matched against prior upstream reports: fpylll #272 ("floating-point exception for linearly dependent matrix", 2024-03-27) and fplll #237 ("numerical stability tests", 2017-02-28). Same failure family, different manifestation. Not a new bug class — a new instance.

## Day 9: the fix

Kahan-compensated subtraction. 30 lines, single hunk. Replaces the naive subtraction with a running compensation term that recaptures the low-order bits lost to each step. Running `make check` on patched fplll: 15/15 pass. Re-ran the 55-seed q=3329 n=100 β=30 1000-bit-MPFR dataset with the patched build: **0 degenerate seeds**.

Paper §8 was rewritten: the finding is not "SD-BKZ is unstable at cryptographic moduli", it's "fplll's squared-form GSO recurrence produces bad output at cryptographic moduli, and here is a patch that fixes it." The paper claims 38.0% → 0% on 55-seed verification and cites `patches/fplll_gso_kahan.patch`.

The upstream issue was drafted (maintained internally pre-filing) but filing was gated on ePrint publication to keep the fix visible upstream before the paper references it. Filing runbook exists internally; the GitHub issue URL will be appended to this doc's Timeline row on filing day.

---

## What changed in the repo

The 9-day cost motivated three concrete policy / infrastructure changes:

### 1. Defensive clamps must log raw values before substituting

The clamp that hid `get_r() = -1.28...` for 9 days was a one-line `if r <= 0: r = 1e-300`. No log of `r`'s actual value. The substitution looked identical across seeds because the clamp constant `1e-300` is identical across seeds. The failure-fingerprint was invisible.

Post-incident rule: every defensive clamp logs the raw pre-substitute value. The repo now has one canonical helper (`scripts/_math_core.log_clamp`) that all clamp sites call. Raw values land in `results/clamp_events.jsonl` as append-only JSONL records — timestamp, script name, seed context, position, raw `get_r()` return value. Grep-able, diff-able across runs, never truncated.

See ADR-001 (`docs/design_decisions.md`) for the deduplication story — before v1.2.0, six different runners each had their own clamp copy with drifted semantics, which was partially why the original incident happened.

### 2. Append-only audit chain

Extended from clamp events to everything. `logs/pipeline.jsonl` receives structured events from every committed script (`scripts/lint_logging.py` enforces this as a CI gate). `results/clamp_events.jsonl` and `logs/pipeline.jsonl` are both strict append-only — never truncated, never rewritten, never deleted.

Policy in [`CONTRIBUTING.md`](../CONTRIBUTING.md): no `rm -rf` over `results/` or any subset, no truncation of append-only files, no rewriting of committed seed JSONs. Corrupted data moves to an explicitly-named in-repo `*_corrupted` directory (when reviewer-visible context matters) or to an offline `_archives/` location (when the audit chain is internal-only). The `_archives/` path is `.gitignore`d in the public repo to keep the boundary clean (INC-39, 2026-04-25). Zero exceptions have been taken.

### 3. Manifest-gated integrity lint

[`scripts/lint_seed_manifest.py`](../scripts/lint_seed_manifest.py) enforces three invariants on every CI run:

- **No orphans**: every file under `results/seeds/<campaign>/` appears in the manifest.
- **No ghosts**: every manifest entry's `path` resolves to an existing file.
- **No drift** (opt-in `--sha-check`): on-disk SHA-256 matches the manifest record.

The gate caught its own regression within 24 hours of shipping — a forward-compat gap in the manifest walker that missed seeds written directly to the v1.3 tree by new runners. That gap was fixed in v1.3.1 (commit `2b5365c`). Exactly the failure the lint was designed to catch: a surprise, contained in one release cycle, not nine days.

---

## What didn't work, and why

Worth recording so future investigations skip them:

- **Running more seeds.** The bimodality was never a sample-size problem. Adding the second machine (Dylan's 9950X3D) and expanding 20 → 45 → 100 seeds reduced CI width but didn't change the central finding; the failure mode doesn't average out.
- **Looking for microarchitecture differences.** Seed 11 bit-identical across Intel 13900K and AMD 9950X3D ruled this out on day 3. Time well-spent for disposing the hypothesis, but not the root-cause path.
- **Increasing MPFR precision.** 250-bit → 500-bit → 1000-bit delays the symptom by a few tours but does not fix it. The root cause is compensated arithmetic, not bit-width. (This shows up in the disclosure doc's "not a precision bug" section.)
- **Staring at aggregate statistics.** Wilson CIs, Cohen's d, per-seed advantage histograms — all beautiful, all wrong layer of abstraction. The raw value was -1.28, not 95% CI [x, y]. A rate-based investigation buries the smoking gun.

## What worked

- **One `get_r(i, i)` capture on one seed at one tour.** 5 minutes once the question was asked. The answer (`-1.28`) flipped the entire investigation.
- **Running the reproducer twice on identical input.** Two runs, two different collapse tours — "hair-trigger near-zero" was directly visible, no stats needed.
- **Mechanical sympathy for the numerical code.** Reading `fplll/gso_interface.cpp:147–151` after seeing the negative value, and recognising the squared-form recurrence as a known cancellation-prone pattern. 10 minutes.
- **Kahan-compensated subtraction as a known remediation.** The patch didn't need to be invented — compensated summation is textbook. The novelty is that fplll didn't have it for this specific loop. 30 lines, verified in an hour.

---

## Timeline

| day | event |
|-----|-------|
| 0   | n=100 q=3329 1000-bit run surfaces bimodal advantage distribution |
| 1–2 | rate-based analysis; Wilson CIs; draft §8 started against clamped output |
| 3   | cross-machine verification (Intel + AMD); bit-identity ruled out microarchitecture |
| 4–5 | concurrency / random-seed hypotheses ruled out; precision-bump hypothesis ruled out |
| 6   | self-review asks "what do raw `get_r()` values look like?" — meta-lesson lands |
| 7   | direct `get_r()` capture produces `-1.2805632996020577` |
| 7   | second reproducer run shows different collapse tour on identical input — "teetering" identified |
| 8   | root cause located at `fplll/gso_interface.cpp:147–151`; matched against fpylll #272 / fplll #237 |
| 9   | Kahan patch drafted; `make check` 15/15 pass; 55-seed rerun 0 degenerate; §8 rewritten |

---

## Related

- Disclosure: [`docs/disclosure/fplll_gso_kahan_findings.md`](disclosure/fplll_gso_kahan_findings.md) — public-facing finding, reproducer, impact.
- Patch: [`patches/fplll_gso_kahan.patch`](../patches/fplll_gso_kahan.patch) + [`patches/README.md`](../patches/README.md).
- Design decisions: [`docs/design_decisions.md`](design_decisions.md) (ADR-001 is the deduplication story that made the clamp-logging rule enforceable).
- Security policy: [`SECURITY.md`](../SECURITY.md) — defensive engineering inventory, all three policy changes above live there.
- Upstream timeline: filing runbook maintained internally; issue URL will appear in the disclosure doc's Timeline once filed.
