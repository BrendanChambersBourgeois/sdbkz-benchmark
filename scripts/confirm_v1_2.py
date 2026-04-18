#!/usr/bin/env python3
"""v1.2-consolidation confirmation suite — regen archived seeds with
the Phase 1-5 refactored code and byte-compare to the paper dataset.

Protocol for each target seed:
  1. Resolve the archive path (where the paper-era seed JSON lives).
  2. Force the refactored runner to compute that seed and write to a
     /tmp staging directory.
  3. Byte-compare staging vs archive, stripping only the three
     metadata fields whose change is expected and harmless
     (timestamp, bkz_time, sdbkz_time).
  4. PASS = numerical content matches; FAIL otherwise. Archives are
     never modified — they stay in place at their original SHA-256.

Tiers (CLI flag `--tier A|B|C|all`):
  A — fast sanity, ~2.3h wall on local 22-core host:
      q=97 n=80  β=30 seeds 1..5  (archive: results/raw/, sweep_parallel)
      q=97 n=100 β=30 seeds 1..5  (archive: results/raw/, sweep_parallel)
  B — cliff region, ~10.8h wall:
      q=97 n=110 β=40 seeds 1..5  (archive: results/cloud/, sweep_parallel)
      q=97 n=130 β=40 seeds 1..5  (archive: results/cloud/, sweep_parallel)
  C — q=3329 + 500-bit precision, ~9h wall (run sequentially):
      q=3329 n=90 β=30 1000-bit seeds 1..5  (archive: results/q3329_n90_beta30/,
          via q3329_verify directly with --precision 1000)
      q=97 n=130 β=40 500-bit seeds 1..5    (archive: results/cliff_500bit/,
          via q3329_verify with Q=97 + MAX_TOURS=100 + 500-bit + store_per_tour=True)

Pre-Phase-5 q3329_verify always emitted `store_per_tour`; the older
mass q3329 archives (results/q3329/, q3329_n70, q3329_n80) predate
this schema. Those are excluded — byte-comparison would fail for
reasons unrelated to Phase 5.

Usage:
  python3 scripts/confirm_v1_2.py --tier A
  python3 scripts/confirm_v1_2.py --tier all
  python3 scripts/confirm_v1_2.py --tier A --dry-run    # plan only
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SCRIPTS)

from log import get_logger, new_run_id, get_run_id  # noqa: E402
PIPELINE = get_logger("confirm_v1_2")

STAGING = "/tmp/confirm_v1_2"
os.makedirs(STAGING, exist_ok=True)

STRIP = {"timestamp", "bkz_time", "sdbkz_time"}


def _strip(path):
    with open(path) as f:
        d = json.load(f)
    for k in STRIP:
        d.pop(k, None)
    return json.dumps(d, sort_keys=True).encode()


def _byte_ok(archive_path, new_path):
    return _strip(archive_path) == _strip(new_path)


def _confirm_group(label, targets, runner_inline, logger=PIPELINE):
    """targets: list of dicts with archive=..., staging=...
    runner_inline: Python code that produces JSONs at the staging paths."""
    print(f"\n=== {label} ===")
    valid_targets = [t for t in targets if os.path.exists(t["archive"])]
    skipped = len(targets) - len(valid_targets)
    if skipped:
        print(f"  Skipping {skipped} (archive missing)")
    if not valid_targets:
        print("  Nothing to confirm.")
        return 0, 0, []
    print(f"  Confirming {len(valid_targets)} seed(s)...")

    # Wipe staging files for these targets so we can detect non-regen
    for t in valid_targets:
        if os.path.exists(t["staging"]):
            os.remove(t["staging"])

    logger.info(f"{label} regen start", cat="validation",
                seeds=len(valid_targets))
    t0 = time.time()
    r = subprocess.run(["python3", "-c", runner_inline],
                       cwd=REPO, capture_output=True, text=True, timeout=86400)
    elapsed = time.time() - t0

    if r.returncode != 0:
        print(f"  RUNNER FAILED (rc={r.returncode}) after {elapsed/60:.1f} min")
        print("  stderr tail:")
        for line in r.stderr.splitlines()[-15:]:
            print(f"    {line}")
        logger.error(f"{label} runner failed", cat="validation",
                     returncode=r.returncode, elapsed_s=int(elapsed))
        return 0, len(valid_targets), [(t["archive"], "runner-fail") for t in valid_targets]

    ok = 0
    fail = 0
    details = []
    for t in valid_targets:
        if not os.path.exists(t["staging"]):
            print(f"  FAIL (not regenerated): {os.path.basename(t['archive'])}")
            fail += 1
            details.append((t["archive"], "not regenerated"))
            continue
        if _byte_ok(t["archive"], t["staging"]):
            ok += 1
        else:
            fail += 1
            details.append((t["archive"], "BYTE-DIFF"))
            print(f"  BYTE-DIFF: {os.path.basename(t['archive'])}")
            print(f"    archive: {t['archive']}")
            print(f"    staging: {t['staging']}")

    print(f"  {label}: {ok}/{ok + fail} PASS  ({elapsed/60:.1f} min)")
    logger.info(f"{label} regen complete", cat="validation",
                ok=ok, fail=fail, elapsed_s=int(elapsed))
    return ok, fail, details


# -- Group builders ---------------------------------------------------------

def _sweep_parallel_group(n, beta, seeds, archive_subdir):
    targets = [
        {
            "archive": os.path.join(REPO, archive_subdir,
                                    f"n{n}_beta{beta}_seed{s}.json"),
            "staging": os.path.join(STAGING,
                                    f"sp_n{n}_b{beta}_s{s}.json"),
        }
        for s in seeds
    ]
    inline = f"""
import sys, json
from multiprocessing import Pool
sys.path.insert(0, 'scripts')
from sweep_parallel import run_single
N, BETA = {n}, {beta}
SEEDS = {list(seeds)!r}
STAGING_TMPL = {os.path.join(STAGING, f'sp_n{{n}}_b{{beta}}_s{{seed}}.json')!r}
def work(s):
    r = run_single(N, BETA, s)
    out = STAGING_TMPL.format(n=N, beta=BETA, seed=s)
    with open(out, 'w') as f:
        json.dump(r, f, indent=2)
    return s
with Pool(len(SEEDS)) as p:
    for s in p.imap_unordered(work, SEEDS):
        print(f'done seed {{s}}', flush=True)
"""
    return (
        f"q=97 n={n} β={beta} seeds {seeds[0]}..{seeds[-1]}  "
        f"(archive: {archive_subdir})",
        targets,
        inline,
    )


def _q3329_n90_group(seeds):
    """q=3329 n=90 β=30 1000-bit seeds via q3329_verify direct call."""
    targets = [
        {
            "archive": os.path.join(REPO, "results/q3329_n90_beta30",
                                    f"n90_beta30_q3329_seed{s}.json"),
            "staging": os.path.join(STAGING, f"q3329_n90_b30_s{s}.json"),
        }
        for s in seeds
    ]
    inline = f"""
import sys, json
from multiprocessing import Pool
sys.argv = ['q3329_verify.py', '--n', '90', '--beta', '30',
            '--seeds', '5', '--precision', '1000']
sys.path.insert(0, 'scripts')
import q3329_verify
SEEDS = {list(seeds)!r}
STAGING_TMPL = {os.path.join(STAGING, 'q3329_n90_b30_s{seed}.json')!r}
def work(s):
    r = q3329_verify.run_single(90, 30, s, store_per_tour=True)
    with open(STAGING_TMPL.format(seed=s), 'w') as f:
        json.dump(r, f, indent=2)
    return s
with Pool(len(SEEDS)) as p:
    for s in p.imap_unordered(work, SEEDS):
        print(f'done seed {{s}}', flush=True)
"""
    return (
        "q=3329 n=90 β=30 seeds 1..5  (1000-bit, archive: results/q3329_n90_beta30/)",
        targets,
        inline,
    )


def _cliff_500_group(seeds):
    """Cliff 500-bit via q3329_verify with Q=97 override."""
    targets = [
        {
            "archive": os.path.join(REPO, "results/cliff_500bit",
                                    f"n130_beta40_q97_seed{s}.json"),
            "staging": os.path.join(STAGING, f"cliff_500_n130_b40_s{s}.json"),
        }
        for s in seeds
    ]
    inline = f"""
import sys, json
from multiprocessing import Pool
sys.argv = ['q3329_verify.py', '--n', '130', '--beta', '40',
            '--seeds', '5', '--precision', '500']
sys.path.insert(0, 'scripts')
import q3329_verify
q3329_verify.Q = 97  # cliff test override
SEEDS = {list(seeds)!r}
STAGING_TMPL = {os.path.join(STAGING, 'cliff_500_n130_b40_s{seed}.json')!r}
def work(s):
    r = q3329_verify.run_single(130, 40, s, store_per_tour=True)
    with open(STAGING_TMPL.format(seed=s), 'w') as f:
        json.dump(r, f, indent=2)
    return s
with Pool(len(SEEDS)) as p:
    for s in p.imap_unordered(work, SEEDS):
        print(f'done seed {{s}}', flush=True)
"""
    return (
        "cliff 500-bit q=97 n=130 β=40 seeds 1..5  "
        "(archive: results/cliff_500bit/)",
        targets,
        inline,
    )


def _tier_a():
    return [
        _sweep_parallel_group(80, 30, list(range(1, 6)), "results/raw"),
        _sweep_parallel_group(100, 30, list(range(1, 6)), "results/raw"),
    ]


def _tier_b():
    return [
        _sweep_parallel_group(110, 40, list(range(1, 6)), "results/cloud"),
        _sweep_parallel_group(130, 40, list(range(1, 6)), "results/cloud"),
    ]


def _tier_c():
    return [
        _q3329_n90_group(list(range(1, 6))),
        _cliff_500_group(list(range(1, 6))),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=["A", "B", "C", "all"], default="A")
    ap.add_argument("--only", default=None,
                    help="Substring filter on group label. Use when "
                         "launching multiple confirm_v1_2 instances in "
                         "parallel so each one writes its own pipeline "
                         "events (e.g. --tier all --only 'n=110').")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    tiers_to_run = {
        "A": [_tier_a()],
        "B": [_tier_b()],
        "C": [_tier_c()],
        "all": [_tier_a(), _tier_b(), _tier_c()],
    }[args.tier]

    all_groups = [g for tier_groups in tiers_to_run for g in tier_groups]
    if args.only:
        all_groups = [g for g in all_groups if args.only in g[0]]
        if not all_groups:
            print(f"No group matches --only {args.only!r}")
            return 1

    print("=" * 70)
    print(f"v1.2-consolidation confirmation — tier {args.tier}")
    for label, targets, _ in all_groups:
        valid = sum(1 for t in targets if os.path.exists(t["archive"]))
        print(f"  {label}  ({valid}/{len(targets)} archives present)")
    print(f"  Staging: {STAGING}")
    print("=" * 70, flush=True)

    if args.dry_run:
        print("DRY-RUN — no regen.")
        return 0

    # Generate a run-id once at the suite level — every subprocess
    # we launch (the inline `python3 -c '...'` runners) inherits it
    # via the BKZ_RUN_ID environment variable, so all events for this
    # confirmation pass group together in pipeline.jsonl analyses.
    run_id = get_run_id() or new_run_id()
    print(f"  run_id: {run_id}", flush=True)
    PIPELINE.info("confirmation suite start", cat="validation",
                  tier=args.tier, groups=len(all_groups))
    total_ok = 0
    total_fail = 0
    all_details = []

    for label, targets, runner in all_groups:
        ok, fail, details = _confirm_group(label, targets, runner)
        total_ok += ok
        total_fail += fail
        all_details.extend(details)

    print()
    print("=" * 70)
    print(f"TIER {args.tier} COMPLETE: {total_ok} PASS / {total_fail} FAIL")
    if all_details:
        print("Failures:")
        for p, msg in all_details:
            print(f"  {p}  :  {msg}")
    print("=" * 70)
    PIPELINE.info("confirmation suite complete", cat="validation",
                  tier=args.tier, ok=total_ok, fail=total_fail)
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
