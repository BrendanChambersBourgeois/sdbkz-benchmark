#!/usr/bin/env python3
"""Forever runner — keep the box producing science, never idle, never spin.

The reconciled MINIMAL design from the 2026-08-08 B2 plan review
(Research/audits/2026-08-08_b2_plan_review.md). One loop:

    every iteration (with a mandatory floor sleep so it can NEVER busy-spin):
      * run the next un-done line of the worklist (real experiments, top priority);
      * if the worklist is drained, add ONE step of idle-filler seeds to the
        SEPARATE ntru_b2 tree (never touches a published cell);
      * archive each worklist line's outcome; stop LOUD after too many
        consecutive failures (a systemic breakage), never churn.

Owner injects higher-value work by editing config/forever_worklist.txt (add a
line, or reorder). The runner NEVER mutates that file — it tracks completed lines
in results/logs/forever_worklist.done — so an edit-while-running can't race a rewrite.

Deploy note: this REPLACES onset_driver as the top-level loop, but is built to run
in isolation first (--dry-run spawns nothing). It takes its OWN lock, distinct from
onset_driver's, and must NOT run concurrently with a live onset_driver on the same
cells. Cutover = stop the old unit at a clean boundary, then start this. Use
systemd Restart=on-failure (NOT always): the loop is designed never to exit on
empty, so any exit is a bug worth leaving stopped-and-visible.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from log import get_logger  # noqa: E402

log = get_logger("forever_runner")

REPO = Path(__file__).resolve().parent.parent
WORKLIST = REPO / "config" / "forever_worklist.txt"       # tracked, owner-editable run-list
DONE_LOG = REPO / "results" / "logs" / "forever_worklist.done"    # runtime (gitignored)
FAILED_LOG = REPO / "results" / "logs" / "forever_worklist.failed"
LOCK = REPO / "results" / "logs" / "forever_runner.lock"

FLOOR_SLEEP_S = 60          # top-of-loop sleep: makes busy-spin structurally impossible
MAX_CONSEC_FAIL = 3         # stop LOUD after this many back-to-back failures (systemic)
FILLER_CAMPAIGN = "ntru_b2_backfill"
FILLER_STEP = 10            # seeds added per idle-filler step
FILLER_WORKERS = 10
# Frontier cells the idle-filler tops up (separate ntru_b2 tree), round-robin to
# the least-sampled, ceiling ratchets so it never exhausts. Low-value BY DESIGN —
# it only runs when the worklist (real science) is empty.
FILLER_CELLS = [(167, 3167), (173, 4073), (179, 4591)]
FILLER_CEILING_START = 60


# --------------------------------------------------------------------------- lock
def acquire_lock() -> bool:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)  # atomic
    except FileExistsError:
        try:
            old = int(LOCK.read_text().strip())
            os.kill(old, 0)
            argv = Path(f"/proc/{old}/cmdline").read_bytes().decode("replace").split("\0")
            if any(os.path.basename(a) == "forever_runner.py" for a in argv):
                log.info("another forever_runner holds the lock -- exiting", cat="runner")
                return False
        except (ValueError, ProcessLookupError, FileNotFoundError, OSError):
            pass
        log.info("stale/foreign lock -- reclaiming", cat="runner")
        fd = os.open(str(LOCK), os.O_CREAT | os.O_TRUNC | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return True


def release_lock() -> None:
    try:
        if LOCK.exists() and int(LOCK.read_text().strip()) == os.getpid():
            LOCK.unlink()
    except (ValueError, FileNotFoundError):
        pass


# ---------------------------------------------------------------------- worklist
def _sig(line: str) -> str:
    return " ".join(line.split())          # whitespace-normalized signature


def _processed() -> set[str]:
    seen: set[str] = set()
    for f in (DONE_LOG, FAILED_LOG):
        if f.exists():
            for ln in f.read_text().splitlines():
                # stored as "<ts>\t<rc>\t<sig>"; recover the signature tail
                parts = ln.split("\t", 2)
                if len(parts) == 3:
                    seen.add(parts[2])
    return seen


def next_worklist_line() -> str | None:
    """First worklist line (non-blank, non-#) not already processed, else None."""
    if not WORKLIST.exists():
        return None
    seen = _processed()
    for ln in WORKLIST.read_text().splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if _sig(s) not in seen:
            return s
    return None


def _record(logfile: Path, rc: int, line: str) -> None:
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with open(logfile, "a") as fh:
        fh.write(f"{int(time.time())}\t{rc}\t{_sig(line)}\n")


# --------------------------------------------------------------------- execution
def _run_campaign(args: list[str], budget_h: float | None, dry: bool) -> int:
    cmd = [sys.executable, str(REPO / "scripts" / "run_campaign.py"), *args]
    if dry:
        log.info(f"[dry-run] would run: {' '.join(args)}", cat="runner")
        return 0
    timeout = budget_h * 3600 if budget_h else None
    try:
        return subprocess.run(cmd, cwd=str(REPO), timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        log.info(f"line hit budget_h={budget_h} -- moving on", cat="runner")
        return 0                                  # budget reached = an intended stop, not a failure


def run_worklist_line(line: str, dry: bool) -> int:
    """Parse '<campaign> [--flags...] [@budget_h=H]' and run it via run_campaign."""
    toks = line.split()
    budget_h = None
    rest = []
    for t in toks:
        if t.startswith("@budget_h="):
            try:
                budget_h = float(t.split("=", 1)[1])
            except ValueError:
                pass
        else:
            rest.append(t)
    if not rest:
        return 2
    campaign, flags = rest[0], rest[1:]
    args = ["--campaign", campaign, *flags]
    log.info(f"START worklist line: {line}", cat="runner")
    rc = _run_campaign(args, budget_h, dry)
    log.info(f"DONE worklist line rc={rc}: {campaign}", cat="runner")
    return rc


def _cell_seed_count(n: int, q: int) -> int:
    d = REPO / "results" / "seeds" / "ntru_b2" / f"q{q}" / "p500_mt50" / f"n{n}_beta40"
    return len(list(d.glob("seed*.json"))) if d.exists() else 0


def run_filler_unit(dry: bool) -> bool:
    """Add one step of idle-filler seeds to the least-sampled ntru_b2 frontier cell.
    Returns True if it did (or would) work, False if every cell is at the ceiling
    (caller then just sleeps -- no busy-spin). Ceiling ratchets so it never truly
    exhausts, but the ratchet only bites after the whole low-value floor is filled."""
    counts = [(_cell_seed_count(n, q), n, q) for (n, q) in FILLER_CELLS]
    counts.sort()
    fewest, n, q = counts[0]
    most = counts[-1][0]
    ceiling = FILLER_CEILING_START + FILLER_STEP * (most // FILLER_CEILING_START)
    if fewest >= ceiling:
        ceiling += FILLER_STEP                    # ratchet: never permanently exhausted
    target = min(fewest + FILLER_STEP, ceiling)
    log.info(f"filler: ntru_b2 n={n} q={q} seeds {fewest}->{target}", cat="runner", event="filler")
    rc = _run_campaign(["--campaign", FILLER_CAMPAIGN, "--n", str(n), "--q", str(q),
                        "--seeds", str(target), "--workers", str(FILLER_WORKERS)], None, dry)
    return rc == 0


# -------------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="log decisions, spawn no campaigns; also caps the loop")
    ap.add_argument("--max-iters", type=int, default=0,
                    help="stop after N iterations (0 = forever; used by --dry-run/tests)")
    args = ap.parse_args(argv)
    if args.dry_run:
        os.environ["PIPELINE_LOG_TAG"] = "dryrun"   # central log, marked synthetic

    if not args.dry_run and not acquire_lock():
        return 0
    consec_fail = 0
    it = 0
    try:
        log.info("==== forever_runner up ====", cat="runner")
        while True:
            it += 1
            if args.max_iters and it > args.max_iters:
                log.info("max-iters reached -- stopping", cat="runner")
                return 0
            if not args.dry_run:
                time.sleep(FLOOR_SLEEP_S)          # FLOOR: busy-spin is impossible
            try:
                line = next_worklist_line()
                if line:
                    rc = run_worklist_line(line, args.dry_run)
                    if not args.dry_run:                 # dry-run must NOT mutate queue state
                        if rc:
                            _record(FAILED_LOG, rc, line)
                        _record(DONE_LOG, rc, line)      # mark done either way (broken line not retried forever)
                    consec_fail = consec_fail + 1 if rc else 0
                else:
                    did = run_filler_unit(args.dry_run)
                    consec_fail = 0 if did else consec_fail
                    if not did and not args.dry_run:
                        time.sleep(FLOOR_SLEEP_S)     # nothing to do -> sleep more, never spin
                if consec_fail >= MAX_CONSEC_FAIL:
                    log.error(f"STOP-LOUD: {consec_fail} consecutive failures -- "
                              f"systemic breakage, not churning", cat="runner",
                              event="stop_loud")
                    return 1
            except Exception as exc:                 # NEVER raise out of the loop
                consec_fail += 1
                log.error(f"iteration error ({consec_fail}/{MAX_CONSEC_FAIL}): {exc!r}",
                          cat="runner", event="iter_error")
                if consec_fail >= MAX_CONSEC_FAIL:
                    log.error("STOP-LOUD: repeated iteration errors", cat="runner",
                              event="stop_loud")
                    return 1
            if args.dry_run and args.max_iters == 0:
                return 0                             # dry-run default: one pass
    finally:
        if not args.dry_run:
            release_lock()
    return 0


if __name__ == "__main__":
    sys.exit(main())
