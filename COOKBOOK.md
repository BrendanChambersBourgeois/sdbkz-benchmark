# Cookbook

Task-oriented snippets for common operations. Assumes you've cloned the repo and installed the dependencies in `pyproject.toml`.

For first-time users: run `python3 examples/01_inspect_one_seed.py` first to confirm everything works, then read the relevant section below.

---

## I want to verify the install works

```bash
bash scripts/verify.sh
```

Runs 5 reference seeds (n=50, β=20) and compares against known-good values. Should print `VERIFICATION PASSED`. If it doesn't, your dependencies don't match the pinned versions in `pyproject.toml`.

---

## I want to reproduce one figure from the paper

```bash
python3 analysis/paper_figures.py
```

Regenerates all 12 figures into `analysis/figures/`. To regenerate one specific figure, edit the bottom of `paper_figures.py` to call only the function you want. Each figure function (`fig_dimension_scaling`, `fig_3x_tour_test`, etc.) is independently callable.

---

## I want to run a few seeds locally without the full sweep

```python
# In a Python REPL:
import sys; sys.path.insert(0, "scripts")
from sweep_parallel import run_single

result = run_single(n=100, beta=30, seed=1)
print(f"Advantage: {result['advantage']:+.4f} nats")
```

Runtime: ~25 minutes for n=100 β=30 (most of it in BKZ, not Python overhead).

---

## I want to add a new dimension to the sweep

Edit `scripts/sweep_parallel.py`:

```python
NS = [50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160]
#                                                          ^ new
```

Then run `nohup python3 scripts/sweep_parallel.py > logs/nohup.out 2>&1 &`. The script is resumable — it skips seeds already present under `results/seeds/main/q97/`.

---

## I want to run only one block size

Edit `BETAS` in `scripts/sweep_parallel.py`:

```python
BETAS = [30]   # was [20, 30, 40]
```

Or run a single (n, beta, seed) directly via the Python REPL using `run_single()` (see the snippet above).

---

## AWS Batch cloud campaign (decommissioned 2026-04-10)

The cloud sweep is no longer live. All AWS Batch + S3 compute was torn
down 2026-04-10 after the q=97 main campaign completed (~4,300 seeds);
the S3 bucket was drained to local + Google Drive. The remaining cloud
scripts (`scripts/submit_jobs.py`, `scripts/sweep_cloud.py`,
`scripts/cloud_watchdog.sh`) are kept on `main` as the audit-chain
record of how those seeds were produced, not as live operational
surface. Re-enabling would require fresh AWS plumbing and a re-pinned
container image. The reference-run path on local hardware is
`python3 scripts/sweep_parallel.py` (see "How do I reproduce the
paper from scratch?" below).

---

## I want to add a new analysis or figure

1. Open `analysis/paper_figures.py`
2. Add a new function `fig_my_thing(groups, output_dir=".")` near the existing figure functions
3. Register it in `generate_all()` near the other `print("--- Figure N ...")` lines
4. Run `python3 analysis/paper_figures.py` to regenerate

The `groups` argument is a `dict[(n, beta)] -> list[seed_dict]` produced by `load_all_seeds()`. Each `seed_dict` has the keys you'd see in any per-seed JSON under `results/seeds/main/q97/...` (advantage, bkz_dln_per_tour, rankin_profile_bkz, etc.).

---

## I want to inspect what fields are in a result file

```python
import sys
sys.path.insert(0, ".")
from analysis._data import load_all_seeds

groups = load_all_seeds(campaign="main", q=97)
d = groups[(100, 30)][0]   # first seed in the (n=100, β=30) cell
print(sorted(d.keys()))
```

Or just run `python3 examples/01_inspect_one_seed.py` which pretty-prints the most useful ones.

---

## I want to compute statistics for a custom group selection

```python
import sys, numpy as np
sys.path.insert(0, ".")
from analysis._data import load_all_seeds

# Load whatever subset you want via the manifest (campaign-keyed
# since v1.3; the legacy `results/raw/`-style glob is gone post-v2).
groups = load_all_seeds(campaign="main", q=97)
advs = np.array([s["advantage"] for s in groups[(100, 30)]])

print(f"mean: {advs.mean():+.4f}, std: {advs.std(ddof=1):.4f}")
print(f"win rate: {(advs > 0).mean()*100:.0f}%")
print(f"Cohen's d: {advs.mean() / advs.std(ddof=1):.2f}")
```

---

## I want to clean up old / failed seeds

Don't delete experimental data — even if it's wrong. Move it to a quarantine folder instead:

```bash
mkdir -p results/corrupted
mv results/seeds/main/q97/n<bad>_beta<bad>/seed<bad>.json results/corrupted/
```

The `results/corrupted/` folder is gitignored. See `CHANGELOG.txt` in the project notes for the q=3329 500-bit precision incidents that drove this convention.

---

## I want to know how long a sweep will take

```python
import sys; sys.path.insert(0, "scripts")
from sweep_parallel import TIMEOUT_BY_BETA

# Approximate per-seed runtime is half the timeout
for beta, timeout_s in TIMEOUT_BY_BETA.items():
    print(f"β={beta}: ~{timeout_s/2/3600:.1f}h per seed (worst case)")
```

For n=100 β=30 the typical seed takes ~25 minutes. For n=150 β=40 it's 6-10 hours. The sweep parallelizes 22 ways on the local VM (configurable via `NUM_WORKERS`).

---

## I'm stuck — where do I look?

1. **`README.md`** — overview, results table, install instructions
2. **`examples/`** — concrete runnable scripts (start here if confused)
3. **`COOKBOOK.md`** — this file, task-oriented
4. **`analysis/paper_figures.py`** — figure code, well-commented
5. **`scripts/sweep_parallel.py`** — the actual experiment loop
