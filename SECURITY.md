# Security policy

This is a research benchmark, not a service. Two things count as security reports here:

1. Numerical-correctness bugs with cryptographic context (lattice reduction informs post-quantum parameter choices).
2. Evidence integrity: the SHA-256 seed manifests, cross-environment bit-identity and append-only logs the papers rely on.

Report to brendanchambersbou@gmail.com with the affected commit or tag and a reproduction path. Acknowledgment within 7 days, triage within 30; no fix timeline is guaranteed. Upstream findings (fplll, fpylll, G6K, MPFR) are coordinated so the fix lands upstream first.

## Withdrawn finding

Paper 1 §8 reported Gram–Schmidt cancellation in fplll at q=3329 and a Kahan-compensated patch ([fplll PR #550](https://github.com/fplll/fplll/pull/550), closed unmerged). Both are withdrawn: the reduction at 1000-bit MPFR is clean and the −345 floors came from this repository's own double-precision measurement GSO (Paper 2, Appendix A). The patch and its disclosure doc left the tree on 2026-10-13.

Out of scope: supply-chain compromise of pinned dependencies (the CI reproducibility gate fails rather than silently drifting), cryptographic protocol design.
