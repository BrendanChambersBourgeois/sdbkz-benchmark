# BKZ Dynamical Systems Benchmark

[![CI](https://github.com/BrendanChambersBourgeois/sdbkz-benchmark/actions/workflows/build-and-verify.yml/badge.svg)](https://github.com/BrendanChambersBourgeois/sdbkz-benchmark/actions)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19686927.svg)](https://doi.org/10.5281/zenodo.19686927)
[![License: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](LICENSE)
[![License: CC-BY-4.0](https://img.shields.io/badge/Paper%20%26%20data-CC--BY--4.0-brightgreen.svg)](https://creativecommons.org/licenses/by/4.0/)

Empirical comparison of self-dual BKZ (SD-BKZ) against BKZ, measured by the distance d(LN) of the reduced basis profile from the Li–Nguyen fixed point. Two engines: fplll 5.5.0 enumeration (13,693 seeds under `results/seed_manifest.json`) and G6K sieving (3,034 seeds under `results/g6k_seed_manifest.json`). Paper 1 (LWE-Kannan, published on Zenodo) lives in `paper1/`; Paper 2 (NTRU dense-sublattice onset and the cross-engine study, in progress) in `paper2/`.

## Quickstart

```bash
git clone https://github.com/BrendanChambersBourgeois/sdbkz-benchmark
cd sdbkz-benchmark
docker build -t sdbkz-benchmark:ci .                             # ~5 min
docker run --rm -e NUM_SEEDS=1 sdbkz-benchmark:ci bash scripts/verify.sh
# expected tail:
#   PASS  seed 1: advantage=0.211363 (ref=0.211363)
#   VERIFICATION PASSED
```

`verify.sh` regenerates one reference seed inside the pinned container and compares it to hardcoded values to 4 decimal places. Run `pytest` and `analysis/paper_figures.py` inside the image too; the host Python is not pinned. If bind-mounted files come out root-owned, rebuild with `--build-arg HOST_UID=$(id -u) --build-arg HOST_GID=$(id -g)`.

Other entry points: `make help` lists the targets; `python3 scripts/run_campaign.py --campaign <name> --dry-run` shows what a campaign in `config/sweep.toml` would run.

## Results (Paper 1, q=97, 100 seeds per cell)

| Dimension | β=20 | β=30 | β=40 |
|---|---|---|---|
| n=50–80 | 98–100% win, d=1.7–2.7 | 100% win, d=2.8–3.0 | 90–100% win, d=1.3–3.6 |
| n=90 | 100% win, d=2.4 | 100% win, d=4.60, mean +0.922 | 100% win, d=3.04 |
| n=100 | 99% win, d=2.12 | 100% win, d=6.20, mean +1.346 | 100% win, d=9.40, mean +1.176 |
| n=110 | 92% win, d=1.47 | 100% win, d=5.64, mean +1.112 | 100% win, d=6.88, mean +1.158 |
| n=120 | 71% win, d=0.60 | 100% win, d=4.97, mean +0.741 | 44% win, mean −0.028 |
| n=130 | 54% win | 100% win, d=3.19, mean +0.352 | 0% win, mean −1.334 |
| n=140 | 22% win | 32% win, mean −0.036 | 0% win, mean −1.452 |
| n=150 | 12% win | 0% win, mean −0.395 | 0% win, mean −1.292 |

Win = SD-BKZ ends closer to the fixed point; d = Cohen's d; mean in nats. The four variance-filled cells carry 122 seeds. Full tables with CIs and p-values are in the paper.

- **β=30 inverted U:** peak at n=100 (+1.346), declining to −0.395 at n=150.
- **β=40 cliff:** 100% win through n=110, 44% at n=120, 0% from n=130. β=40's peak is not resolvable between n=100 and n=110 (122 seeds each, bootstrap CI of the difference [−0.032, +0.043]); Paper 1's "n=110" is superseded.
- **β/n ≈ 0.20:** below this ratio the advantage fades and reverses.
- **Convergence is regime-dependent:** at n=90 β=30 SD-BKZ keeps gaining to tour 500 (+0.92 to +1.33); at n=140 β=30 BKZ wins at full convergence.
- **3× tours do not close the gap:** BKZ at 210 tours never matches SD-BKZ at 70 (0/400 at β=30, n=50–80).
- **RHF is blind to it:** at n=100 β=30, d(LN) shows 100% win, RHF 40%, r=−0.08.
- **q=3329 (Paper 1 §8), withdrawn:** the −345 floors at n=100 β=30 came from a double-precision measurement GSO in this code, not from fplll; the reduction at 1000-bit MPFR is clean. The Kahan patch and the fplll attribution are withdrawn (Paper 2, Appendix A).
- SD-BKZ costs 2.3–2.7× the BKZ runtime.

## Data

Each seed is one JSON under `results/seeds/<tree>/q<q>/p<precision>_mt<tours>/n<n>_beta<β>/seedNNNN.json`: inputs, final d(LN) for both algorithms, termination reason, wall time. A `_fat` companion holds per-tour trajectories when the campaign stored them. Field contract: `docs/seed_manifest_schema.md`. Every writer routes through `scripts/_seed_paths.py`; every reader goes through `analysis/_data.py::load_all_seeds`, which queries the manifest and checks SHA-256 on read.

Trees are separate per engine and per build (`ntru` vs `ntru_g6k`, `ntru_g6k_reject` for the reject-on-overflow G6K build, `*_exact`, `*_mpfr`); the two engine manifests are never merged. Trees outside the manifests are listed in `NON_MANIFEST_SEED_TREES` in `scripts/lint_seed_manifest.py`. Pre-v2 paths resolve through `results/seed_path_crosswalk.csv`.

Supplementary: `results/paper_claims/` (one JSON per paper claim with its source seeds), `results/profile_decomposition.json`, `results/hash_verification.txt` (100 seeds bit-identical across two environments).

## Reproducibility

Images are digest-pinned with apt frozen to a dated snapshot (`Dockerfile`; `Dockerfile.g6k` source-builds fplll, fpylll and G6K at `-march=x86-64-v2 --disable-native`; tags and build args in `docs/images.md`). G6K runs at `threads=1`, the only setting where it is byte-reproducible. CI on every push: Docker build, ruff, mypy on the numerical core, pytest with a 75% coverage floor, `verify.sh`, `verify_g6k.sh` exact-SHA gate, `validate_seeds.py`, manifest lints, figure parity. Design records in `docs/design_decisions.md`.

Hosts: Intel 13900K (Ubuntu 24.04, MPFR 4.2.1), AWS Batch (Debian bookworm, MPFR 4.2.0, decommissioned 2026-04-10), AMD 9950X3D spot checks, and a Valve Steam Machine (SteamOS, rootless podman) as a second node for the G6K frontier cells. Software: Python 3.12.3, fpylll 0.6.4, fplll 5.5.0, numpy 2.4.4, cysignals 1.12.6.

## Papers

`paper1/latex/sdbkz_paper_latex.tex` is canonical; `paper1/latex/sdbkz_paper_latex.pdf` and `paper1/sdbkz_paper.html` are built from it (`make paper`). `paper2/latex/` follows the same flow. `patches/` holds the two G6K `gauss_sieve` patches the sieve images apply.

## License and citation

Code: [MIT](LICENSE). Papers and data (`paper1/`, `paper2/`, `results/`): [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/). Cite via `CITATION.cff` or DOI 10.5281/zenodo.19686927.

## Acknowledgements

Dylan Chambers Bourgeois contributed AMD 9950X3D compute and cross-architecture verification. Trill White (Deakin University) gave early feedback on the results.

## References

- Li, J. & Nguyen, P.Q. (2024). A Complete Analysis of the BKZ Lattice Reduction Algorithm. *Journal of Cryptology*; ePrint 2020/1237.
- Micciancio, D. & Walter, M. (2016). Practical, Predictable Lattice Basis Reduction. *EUROCRYPT 2016*.
- [fplll](https://github.com/fplll/fplll), [fpylll](https://github.com/fplll/fpylll), [G6K](https://github.com/fplll/g6k).

The papers' full bibliographies are in `paper1/latex/` and `paper2/latex/`.
