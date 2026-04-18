#!/usr/bin/env python3
"""
Submit all remaining (n, beta) groups to AWS Batch.
Splits each group into jobs of SEEDS_PER_JOB seeds (default 25).

Usage:
    python3 submit_jobs.py                    # submit all pending groups
    python3 submit_jobs.py --dry-run          # show what would be submitted
    python3 submit_jobs.py --vcpus 8          # override vCPUs per job
    python3 submit_jobs.py --n 100 --beta 30  # submit one specific group
    python3 submit_jobs.py --n 150 --beta 40 --single-seed --vcpus 2  # 1 seed per job
"""
import argparse
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from log import get_logger
    slog = get_logger("submit_jobs")
except Exception:
    class _Noop:
        def __getattr__(self, _): return lambda *a, **k: None
    slog = _Noop()
import boto3
import json

JOB_QUEUE = "bkz-job-queue"
JOB_DEFINITION = "bkz-sweep-small:1"
BUCKET = "bkz-benchmark-results"
SEEDS_PER_JOB = 25
MAX_VCPUS = 128

# Recommended vCPUs based on expected per-seed runtime
# Higher β and n = longer seeds = fewer workers needed (more jobs in parallel)
VCPU_RECOMMENDATIONS = {
    20: {(0, 100): 4, (100, 999): 4},     # β=20: fast seeds, keep small
    30: {(0, 100): 8, (100, 140): 8, (140, 999): 4},  # β=30: moderate, 8 is sweet spot
    40: {(0, 80): 8, (80, 130): 4, (130, 999): 4},    # β=40: slow seeds, keep small for max parallelism
}


def recommend_vcpus(n, beta):
    """Suggest vCPUs based on (n, beta) runtime characteristics."""
    ranges = VCPU_RECOMMENDATIONS.get(beta, {(0, 999): 4})
    for (lo, hi), vcpus in ranges.items():
        if lo <= n < hi:
            return vcpus
    return 4


def estimate_memory(vcpus):
    """Estimate memory needed based on vCPUs (1.75 GB per vCPU)."""
    return vcpus * 1792


CLOUD_GROUPS = [
    (100, 20), (100, 30), (100, 40),
    (110, 20), (110, 30), (110, 40),
    (120, 40),
    (130, 30), (130, 40),
    (140, 30), (140, 40),
    (150, 20), (150, 30), (150, 40),
]


def check_completed(n, beta, q=97):
    """Count completed seeds in S3."""
    import re
    s3 = boto3.client("s3")
    if q != 97:
        prefix = f"results/raw/n{n}_beta{beta}_q{q}_seed"
        pattern = re.compile(rf"^n{n}_beta{beta}_q{q}_seed(\d+)\.json$")
    else:
        prefix = f"results/raw/n{n}_beta{beta}_seed"
        pattern = re.compile(rf"^n{n}_beta{beta}_seed(\d+)\.json$")
    count = 0
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                fname = obj["Key"].split("/")[-1]
                if pattern.match(fname):
                    count += 1
    except Exception:
        pass
    return count


def submit_job(n, beta, seed_start, seed_end, vcpus, memory, workers, dry_run=False, q=97, precision=None):
    """Submit one (n, beta, seed_range) job to AWS Batch."""
    job_name = f"bkz-n{n}-b{beta}-s{seed_start}-{seed_end}"
    if q != 97:
        job_name = f"bkz-n{n}-b{beta}-q{q}-s{seed_start}-{seed_end}"

    if dry_run:
        extra = f", q={q}, precision={precision}" if q != 97 else ""
        print(f"  [DRY RUN] {job_name}  ({vcpus} vCPUs, {workers} workers, {memory} MB{extra})")
        slog.info(f"dry-run: {job_name}", cat="sweep",
                  n=n, beta=beta, seed_start=seed_start, seed_end=seed_end,
                  vcpus=vcpus, workers=workers, dry_run=True)
        return

    cmd = [
        "--n", str(n),
        "--beta", str(beta),
        "--bucket", BUCKET,
        "--seed-start", str(seed_start),
        "--seed-end", str(seed_end),
        "--workers", str(workers),
    ]
    if q != 97:
        cmd.extend(["--q", str(q)])
    if precision:
        cmd.extend(["--precision", str(precision)])

    batch = boto3.client("batch")
    response = batch.submit_job(
        jobName=job_name,
        jobQueue=JOB_QUEUE,
        jobDefinition=JOB_DEFINITION,
        containerOverrides={
            "vcpus": vcpus,
            "memory": memory,
            "command": cmd,
        }
    )

    job_id = response["jobId"]
    print(f"  Submitted: {job_name} → {job_id}  ({vcpus} vCPUs, {workers} workers)")
    slog.warning(f"submitted to AWS Batch: {job_name} → {job_id}", cat="sweep",
                 n=n, beta=beta, seed_start=seed_start, seed_end=seed_end,
                 vcpus=vcpus, workers=workers, job_id=job_id, queue=JOB_QUEUE)
    return job_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--beta", type=int, default=None)
    parser.add_argument("--vcpus", type=int, default=None, help="Override vCPUs per job (default: auto-recommend)")
    parser.add_argument("--q", type=int, default=97, help="LWE modulus (default: 97)")
    parser.add_argument("--precision", type=int, default=None, help="MPFR precision in bits (default: auto)")
    parser.add_argument("--single-seed", action="store_true",
                        help="Submit 1 seed per job for max parallelism (use with --vcpus 2)")
    parser.add_argument("--seeds-per-job", type=int, default=None,
                        help="Override seeds per job (default: 25, or 1 with --single-seed)")
    args = parser.parse_args()

    if args.n and args.beta:
        groups = [(args.n, args.beta)]
    else:
        groups = CLOUD_GROUPS

    seeds_per_job = args.seeds_per_job or (1 if args.single_seed else SEEDS_PER_JOB)

    # Split each group into chunks
    all_jobs = []
    for n, beta in sorted(groups):
        vcpus = args.vcpus or (2 if args.single_seed else recommend_vcpus(n, beta))
        memory = estimate_memory(vcpus)
        workers = 1 if args.single_seed else max(1, vcpus - 1)
        for start in range(1, 101, seeds_per_job):
            end = min(start + seeds_per_job - 1, 100)
            all_jobs.append((n, beta, start, end, vcpus, memory, workers))

    done = {}
    for n, beta in sorted(set((n, b) for n, b, _, _, _, _, _ in all_jobs)):
        done[(n, beta)] = check_completed(n, beta, q=args.q)

    max_concurrent = MAX_VCPUS // all_jobs[0][4] if all_jobs else 0

    print(f"Submitting {len(all_jobs)} job(s) across {len(groups)} group(s) to AWS Batch")
    print(f"  Queue: {JOB_QUEUE}")
    print(f"  Definition: {JOB_DEFINITION}")
    print(f"  Bucket: {BUCKET}")
    print(f"  Seeds per job: {seeds_per_job}")
    print(f"  Max concurrent jobs: ~{max_concurrent} (at {MAX_VCPUS} max vCPUs)")
    print()

    print(f"  {'Group':<16} {'Done':>6} {'vCPUs':>6} {'Workers':>8} {'Recommendation'}")
    print(f"  {'-'*60}")
    seen = set()
    for n, beta, _, _, vcpus, _, workers in all_jobs:
        if (n, beta) in seen:
            continue
        seen.add((n, beta))
        rec = recommend_vcpus(n, beta)
        note = "" if vcpus == rec else f" (override, recommended: {rec})"
        print(f"  n={n:<3} β={beta:<2}      {done[(n,beta)]:>3}/100  {vcpus:>4}    {workers:>6}    {note}")
    print()

    job_ids = []
    for n, beta, start, end, vcpus, memory, workers in all_jobs:
        jid = submit_job(n, beta, start, end, vcpus, memory, workers, dry_run=args.dry_run, q=args.q, precision=args.precision)
        if jid:
            job_ids.append({"n": n, "beta": beta, "seeds": f"{start}-{end}", "job_id": jid})

    if job_ids and not args.dry_run:
        print(f"\n{len(job_ids)} jobs submitted. Monitor at:")
        print(f"  aws batch list-jobs --job-queue {JOB_QUEUE} --job-status RUNNING")


if __name__ == "__main__":
    main()
