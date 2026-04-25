#!/usr/bin/env bash
set -euo pipefail

# NOTE: This script is currently DORMANT. The health-check cron was
# removed on 2026-04-07 (handoverv2 §5) when the local sweep finished
# and the cloud took over. The script is kept for the archival record
# of how the local sweep was monitored, and could be re-enabled by
# adding the cron entry back (commented at the bottom of this file).
# Path references were updated for the post-2026-04-08 repo restructure.

BASE="$HOME/Desktop/lattice"
SCRIPTS_DIR="$BASE/scripts"
RAW_DIR="$BASE/results/raw"
BACKUP_BASE="$BASE/results/backups"
MAX_BACKUPS=3

# Logging policy (per Research/backlog/_shipped legacy_log_cleanup):
# - Terminal output stays on stdout (this script is cron-driven; the
#   cron mailer captures stdout if a maintainer wants email per run)
# - Machine-readable events flow through scripts/log.py to
#   logs/pipeline.jsonl with cat=health, so jq queries can filter
#   `select(.cat=="health")` for the dormant-script audit trail.
# The dual emission used to write to results/health.log via `tee -a`;
# that file was retired 2026-04-20 (see commit dropping it).
log() {
    local msg="$1"
    echo "$(date '+%Y-%m-%d %H:%M:%S')  $msg"
    HC_MSG="$msg" PYTHONPATH="$SCRIPTS_DIR" python3 -c "
import os
from log import get_logger
get_logger('health_check').info(os.environ['HC_MSG'], cat='health')
" 2>/dev/null || true
}

log "=== Health check started ==="

# --- 1. Validate all raw JSON files ---
bad=0
total=0
for f in "$RAW_DIR"/*.json; do
    [ -f "$f" ] || continue
    total=$((total + 1))
    if ! python3 -c "import json; json.load(open('$f'))" 2>/dev/null; then
        bad=$((bad + 1))
        log "CORRUPT: $f"
    fi
done
log "JSON validation: $total files checked, $bad corrupt"

# --- 2/3. Check process, restart if needed ---
if pgrep -f "python3.*sweep_parallel\.py" >/dev/null 2>&1; then
    pid=$(pgrep -f "python3.*sweep_parallel\.py" | head -1)
    log "Process alive (PID $pid)"
else
    log "Process NOT running — restarting"
    cd "$BASE" && nohup python3 -u "$SCRIPTS_DIR/sweep_parallel.py" >> sweep_stdout.log 2>&1 &
    sleep 2
    if pgrep -f "python3.*sweep_parallel\.py" >/dev/null 2>&1; then
        pid=$(pgrep -f "python3.*sweep_parallel\.py" | head -1)
        log "Restarted successfully (PID $pid)"
    else
        log "ERROR: restart failed"
    fi
fi

# --- 4. Backup results/raw/ (keep last 3) ---
if [ "$total" -gt 0 ]; then
    stamp=$(date '+%Y%m%d_%H%M')
    dest="$BACKUP_BASE/backup_$stamp"
    mkdir -p "$dest"
    cp "$RAW_DIR"/*.json "$dest/"
    copied=$(ls "$dest"/*.json 2>/dev/null | wc -l)
    log "Backup: $copied files → $dest"

    # Prune old backups, keep newest MAX_BACKUPS
    num_backups=$(ls -dt "$BACKUP_BASE"/backup_* 2>/dev/null | wc -l)
    if [ "$num_backups" -gt "$MAX_BACKUPS" ]; then
        ls -dt "$BACKUP_BASE"/backup_* | tail -n +$((MAX_BACKUPS + 1)) | while read -r old; do
            rm -rf "$old"
            log "Pruned old backup: $old"
        done
    fi
else
    log "Backup: skipped (no files to back up)"
fi

log "=== Health check complete ==="
