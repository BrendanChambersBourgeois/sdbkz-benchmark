# Estimator d(LN) probe — status + queued seed task

Branch `estimator-dln-probe` (worktree off main). Probe for the #1 lever:
does d(LN) reveal a real-BKZ-vs-estimator-model gap big enough to move
deployed bit-security? Separate from paper 2.

## Chain of findings
1. **GSA model (gsa_model.py, no Sage):** estimator assumes GSA; δ_β PEAKS at
   β≈40 then improves toward 1. Deployed β≈400-600 is past the peak. Lever
   1 β ≈ 0.292 bits.
2. **Toy empirical (empirical_probe.py, dim50, β≤40):** d(real,CN11) ~0.027,
   flat in β. Looked like NO-GO -- BUT dim50 is the FLOOR, missed the dim axis.
3. **Firmed over existing main LWE seeds (cn11_firm.py, 3593 seeds, real dims):**
   d(real,CN11) GROWS STRONGLY with dim (β20: n50 0.055 -> n150 0.241, ~4x;
   β40: n90 0.028 -> n150 0.204, ~7x), and SHRINKS with β (β20 0.118 > β40
   0.078). Two competing trends; deployed has BOTH high dim + high β.
   **Overturns the toy NO-GO -> REOPENED.**
4. **Convergence disambiguation (cn11_converge.py):** BLOCKED -- convergence
   mt1000 seeds lack profile fields (only per-tour dln stored). Trajectory
   plateau check INCONCLUSIVE (high-dim converged by ratio, but last-20-tour
   motion ~0.13 ≈ residual ~0.20).

## OPEN QUESTION (the GO/NO-GO decider)
Is the dim-growth of d(real,CN11) a CONVERGENCE artifact (real BKZ under-
trained at high dim / fixed tours) or STRUCTURAL (real fixed point differs
from CN11, growing with dim toward deployed scale)?

## QUEUED SEED TASK (add to the ball-out list; HEAVY, run when cores free)
- **n=130, β=40, tours ∈ {100 (exists in main), 500 (new)}, ~8 seeds each,
  STORE FULL PROFILES** (initial_gs_lognorms + gs_lognorms_bkz).
- Compare d(real,CN11) at mt100 vs mt500 (cn11_converge.py, once profiled
  mt500 seeds exist):
  - SHRINKS (ratio <0.6) -> undertraining artifact -> NO-GO, drop it.
  - STABLE (ratio >0.85) -> structural -> GO, worth a real check at deployed
    dim + the §6 scoping note in paper 2.
- Cost ~13h (n130 β40 mt500 ~35h/seed, 8 seeds / 22 workers). Heavy BKZ --
  competes with n113 + ball-out, so QUEUE, don't run alongside.
- Optional cheaper proxy: n=110 β40 mt100 vs mt500 (~7h) -- residual smaller
  there (0.042) so signal weaker, but cheaper first look.

## If GO: paper-2 §6 scoping note (preliminary), NOT a results section.
"d(LN) structure does/doesn't propagate to security estimation" -- complements
the paper-1 RHF-blind thesis. Only after the disambiguation lands.

## Files
gsa_model.py · empirical_probe.py · cn11_firm.py · cn11_converge.py
_lattice_estimator/ = the cloned malb estimator (untracked, needs Sage to run).
