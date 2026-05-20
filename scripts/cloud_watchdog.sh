#!/usr/bin/env bash
set -euo pipefail
#
# Cloud watchdog: terminates Batch jobs that stop producing results.
# Timeout is per-beta: 2h for β=20, 4h for β=30, 6h for β=40.
# Safe to run via cron every minute.
#
# Usage:
#   bash scripts/cloud_watchdog.sh
#   */1 * * * * bash /path/to/sdbkz-benchmark/scripts/cloud_watchdog.sh
#
# Operator-only: assumes AWS CLI configured for the job queue / bucket
# below, and is retained for future cloud runs; the v1.0 campaign's
# cloud compute environments are decommissioned.

LOCKFILE="/tmp/bkz-cloud-watchdog.lock"
BUCKET="bkz-benchmark-results"
JOB_QUEUE="bkz-job-queue"
REGION="ap-southeast-2"

# Per-beta idle timeout in seconds.
# β=40 at n≥100 needs >6h per seed (100 tours on dim 301+).
# q=3329 at 1000-bit precision may need 10-15h per seed at β=30.
# β=40 raised from 6h to 24h after an early campaign killed all β=40
# jobs at the 6h mark. q=3329 timeouts lifted to the 32-48h range
# after 500-bit precision proved insufficient at n≥100 and the
# campaign moved to 1000-bit MPFR.
get_max_idle() {
    local beta=$1
    local q=${2:-97}
    # q=3329 gets longer timeouts — 1000-bit precision is much slower
    if [ "$q" != "97" ]; then
        case $beta in
            20) echo 14400 ;;   # 4 hours
            30) echo 115200 ;;  # 32 hours (1000-bit seeds ~10-15h each)
            40) echo 172800 ;;  # 48 hours
            *)  echo 115200 ;;  # default 32 hours
        esac
    else
        case $beta in
            20) echo 7200 ;;    # 2 hours
            30) echo 28800 ;;   # 8 hours
            40) echo 86400 ;;   # 24 hours (raised from an earlier 6h limit)
            *)  echo 28800 ;;   # default 8 hours
        esac
    fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() {
    local msg="$1"
    local level="${2:-INFO}"
    # Emit to centralized pipeline.jsonl
    python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from log import get_logger
log = get_logger('cloud_watchdog')
level_map = {'INFO': log.info, 'WARNING': log.warning, 'ERROR': log.error, 'INCIDENT': log.incident}
fn = level_map.get('$level', log.info)
fn(${msg@Q}, cat='sweep')
" 2>/dev/null || true
}

# Lockfile — exit if another instance is running
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    exit 0
fi

log "=== Watchdog check started ==="

# Get all running jobs
RUNNING_JSON=$(aws batch list-jobs \
    --job-queue "$JOB_QUEUE" \
    --job-status RUNNING \
    --region "$REGION" \
    --output json 2>/dev/null) || {
    log "ERROR: aws batch list-jobs failed (exit $?). Aborting." ERROR
    exit 1
}

JOB_COUNT=$(echo "$RUNNING_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['jobSummaryList']))")
log "Running jobs: $JOB_COUNT"

if [ "$JOB_COUNT" -eq 0 ]; then
    log "No running jobs. Done."
    exit 0
fi

# Extract job IDs
JOB_IDS=$(echo "$RUNNING_JSON" | python3 -c "
import sys, json
jobs = json.load(sys.stdin)['jobSummaryList']
for j in jobs:
    print(j['jobId'])
")

NOW=$(date +%s)
TERMINATED=0

for JOB_ID in $JOB_IDS; do
    # Get job details
    JOB_JSON=$(aws batch describe-jobs \
        --jobs "$JOB_ID" \
        --region "$REGION" \
        --output json 2>/dev/null) || {
        log "ERROR: aws batch describe-jobs failed for $JOB_ID. Aborting." ERROR
        exit 1
    }

    # Parse job info including seed range for per-job S3 tracking
    INFO=$(echo "$JOB_JSON" | python3 -c "
import sys, json
j = json.load(sys.stdin)['jobs'][0]
name = j['jobName']
started = j.get('startedAt', 0) // 1000  # ms to seconds
cmd = j.get('container', {}).get('command', [])
n = beta = seed_start = seed_end = ''
q = '97'
for i, c in enumerate(cmd):
    if c == '--n' and i+1 < len(cmd): n = cmd[i+1]
    if c == '--beta' and i+1 < len(cmd): beta = cmd[i+1]
    if c == '--seed-start' and i+1 < len(cmd): seed_start = cmd[i+1]
    if c == '--seed-end' and i+1 < len(cmd): seed_end = cmd[i+1]
    if c == '--q' and i+1 < len(cmd): q = cmd[i+1]
print(f'{name}|{started}|{n}|{beta}|{seed_start}|{seed_end}|{q}')
") || {
        log "ERROR: Failed to parse job info for $JOB_ID. Aborting." ERROR
        exit 1
    }

    JOB_NAME=$(echo "$INFO" | cut -d'|' -f1)
    STARTED_AT=$(echo "$INFO" | cut -d'|' -f2)
    N=$(echo "$INFO" | cut -d'|' -f3)
    BETA=$(echo "$INFO" | cut -d'|' -f4)
    SEED_START=$(echo "$INFO" | cut -d'|' -f5)
    SEED_END=$(echo "$INFO" | cut -d'|' -f6)
    Q_VAL=$(echo "$INFO" | cut -d'|' -f7)

    if [ -z "$N" ] || [ -z "$BETA" ]; then
        log "  $JOB_NAME ($JOB_ID): could not parse n/beta from command. Skipping."
        continue
    fi

    # Guard: if startedAt is 0 or missing, the job just transitioned to RUNNING
    # and the API hasn't populated the field yet. Skip to avoid false kills.
    # But enforce a hard ceiling using createdAt — no job should run >48h total.
    if [ "$STARTED_AT" -eq 0 ] 2>/dev/null || [ -z "$STARTED_AT" ]; then
        log "  $JOB_NAME ($JOB_ID): startedAt not yet populated. Skipping."
        continue
    fi

    # Hard safety ceiling: max total job runtime before unconditional kill.
    # This is NOT the idle timeout — it's the absolute max wall time for a job.
    # A job with 25 seeds at 7 workers needs ~4 batches. Per-seed time varies
    # by beta and dimension. 7 days matches the Batch job definition timeout.
    # If a job runs longer than this, something is fundamentally broken.
    HARD_CEILING=604800  # 7 days in seconds (matches Batch job timeout)
    JOB_AGE=$((NOW - STARTED_AT))
    JOB_AGE_H=$((JOB_AGE / 3600))
    if [ "$JOB_AGE" -gt "$HARD_CEILING" ]; then
        HARD_CEILING_H=$((HARD_CEILING / 3600))
        log "  SAFETY KILL: $JOB_NAME ($JOB_ID) n=${N} β=${BETA} age=${JOB_AGE_H}h limit=${HARD_CEILING_H}h — INCIDENT: job exceeded hard ceiling. Do NOT auto-resubmit." INCIDENT
        aws batch terminate-job \
            --job-id "$JOB_ID" \
            --reason "Safety ceiling: running ${JOB_AGE_H}h (max ${HARD_CEILING_H}h). Manual investigation required." \
            --region "$REGION" 2>/dev/null || {
            log "ERROR: aws batch terminate-job failed for $JOB_ID. Aborting." ERROR
            exit 1
        }
        TERMINATED=$((TERMINATED + 1))
        continue
    fi

    # Check latest S3 file for this job's specific seed range.
    # If seed range is available, only count seeds in that range so
    # sibling jobs in the same group don't mask a hung job by producing
    # fresh S3 keys in the shared prefix.
    #
    # v2.0.0: prefix tracks the v1.3 campaign tree
    # (`results/seeds/<campaign>/...` — same layout as the on-disk
    # tree post-symlink-drop). Cloud campaign is decommissioned
    # (2026-04-10); on any future restart the cloud-side writer
    # (sweep_cloud.s3_key) lands seeds at the same prefix the watchdog
    # now scans. Filenames end with `_cloud.json` on the cloud side
    # (per `_seed_paths._leaf_name` cloud=True suffix).
    if [ "$Q_VAL" != "97" ] && [ -n "$Q_VAL" ]; then
        N_PAD=$(printf "%03d" "$N")
        BETA_PAD=$(printf "%02d" "$BETA")
        S3_PREFIX="results/seeds/q3329/p${PRECISION:-1000}_mt${MAX_TOURS:-70}/n${N_PAD}_beta${BETA_PAD}/seed"
    else
        N_PAD=$(printf "%03d" "$N")
        BETA_PAD=$(printf "%02d" "$BETA")
        S3_PREFIX="results/seeds/main/q97/n${N_PAD}_beta${BETA_PAD}/seed"
    fi
    S3_LIST=$(aws s3api list-objects-v2 \
        --bucket "$BUCKET" \
        --prefix "$S3_PREFIX" \
        --output json \
        --region "$REGION" 2>/dev/null) || {
        log "ERROR: aws s3api list-objects-v2 failed for n=${N} β=${BETA}. Aborting." ERROR
        exit 1
    }

    LATEST_S3=$(echo "$S3_LIST" | python3 -c "
import sys, json, re
data = json.load(sys.stdin)
contents = data.get('Contents', [])
seed_start = '$SEED_START'
seed_end = '$SEED_END'
# Filter to this job's seed range if available
if seed_start and seed_end:
    try:
        lo, hi = int(seed_start), int(seed_end)
        filtered = []
        for obj in contents:
            m = re.search(r'seed(\d+)\.json$', obj['Key'])
            if m and lo <= int(m.group(1)) <= hi:
                filtered.append(obj)
        contents = filtered
    except ValueError:
        pass  # fall back to all seeds
if not contents:
    print('None')
else:
    latest = max(contents, key=lambda x: x['LastModified'])
    print(latest['LastModified'])
" 2>/dev/null) || LATEST_S3="None"

    # Calculate idle time
    if [ "$LATEST_S3" = "None" ] || [ -z "$LATEST_S3" ]; then
        # No S3 files at all — use job start time
        LAST_ACTIVITY=$STARTED_AT
        LAST_SOURCE="job_start"
    else
        LAST_S3_EPOCH=$(date -d "$LATEST_S3" +%s 2>/dev/null || echo "0")
        # Use whichever is more recent: last S3 file or job start
        if [ "$LAST_S3_EPOCH" -gt "$STARTED_AT" ]; then
            LAST_ACTIVITY=$LAST_S3_EPOCH
            LAST_SOURCE="s3_file"
        else
            # S3 files are from a previous job run, use job start time
            LAST_ACTIVITY=$STARTED_AT
            LAST_SOURCE="job_start"
        fi
    fi

    IDLE=$((NOW - LAST_ACTIVITY))
    IDLE_MIN=$((IDLE / 60))
    MAX_IDLE=$(get_max_idle "$BETA" "$Q_VAL")
    MAX_IDLE_MIN=$((MAX_IDLE / 60))

    if [ "$IDLE" -gt "$MAX_IDLE" ]; then
        log "  TERMINATE: $JOB_NAME ($JOB_ID) n=${N} β=${BETA} idle=${IDLE_MIN}m limit=${MAX_IDLE_MIN}m (last=$LAST_SOURCE)" WARNING
        aws batch terminate-job \
            --job-id "$JOB_ID" \
            --reason "Watchdog: no progress for ${IDLE_MIN}m" \
            --region "$REGION" 2>/dev/null || {
            log "ERROR: aws batch terminate-job failed for $JOB_ID. Aborting." ERROR
            exit 1
        }
        TERMINATED=$((TERMINATED + 1))
    else
        log "  OK: $JOB_NAME ($JOB_ID) n=${N} β=${BETA} idle=${IDLE_MIN}m (last=$LAST_SOURCE)"
    fi
done

log "=== Watchdog done: $JOB_COUNT checked, $TERMINATED terminated ==="
