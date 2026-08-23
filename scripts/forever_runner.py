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
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pidlock import acquire_pidlock, release_pidlock  # noqa: E402
from log import get_logger  # noqa: E402

log = get_logger("forever_runner")

REPO = Path(__file__).resolve().parent.parent
WORKLIST = REPO / "config" / "forever_worklist.txt"       # tracked, owner-editable run-list
DONE_LOG = REPO / "results" / "logs" / "forever_worklist.done"    # runtime (gitignored)
FAILED_LOG = REPO / "results" / "logs" / "forever_worklist.failed"
LOCK = REPO / "results" / "logs" / "forever_runner.lock"

FLOOR_SLEEP_S = 60          # top-of-loop sleep: makes busy-spin structurally impossible
MAX_CONSEC_FAIL = 3         # stop LOUD after this many back-to-back failures (systemic)
# Hard wall-clock backstop for ANY campaign child that has no explicit @budget_h.
# INC-54: a beta50 probe hot-wedged ~25h inside one fplll enum call (1 core pinned,
# no heartbeat) and, with timeout=None, would have run forever -- the R1 watchdog's
# CPU-idle gate cannot see a single-core wedge on a 24-core box. A finite default cap
# turns every wedge into a self-terminate. A line that legitimately needs longer MUST
# carry an explicit @budget_h=H (which overrides this, up OR down).
DEFAULT_MAX_WALL_H = 24
FILLER_CAMPAIGN = "ntru_b2_backfill"
FILLER_STEP = 10            # seeds added per idle-filler step
FILLER_WORKERS = 10
# Frontier cells the idle-filler tops up (separate ntru_b2 tree), round-robin to
# the least-sampled, ceiling ratchets so it never exhausts. Low-value BY DESIGN —
# it only runs when the worklist (real science) is empty.
FILLER_CELLS = [(167, 3167), (173, 4073), (179, 4591)]
FILLER_CEILING_START = 60
FILLER_TREE = "ntru_b2"      # seed tree the filler writes = seed_tag of FILLER_CAMPAIGN


# --------------------------------------------------- child process + signal safety
_CURRENT_CHILD: subprocess.Popen[bytes] | None = None   # the in-flight campaign, for kill-on-signal


def _kill_child_group(p: subprocess.Popen[bytes] | None) -> None:
    """SIGTERM then SIGKILL the child's whole process group. run_campaign spawns its
    own worker pool; killing only the direct child would orphan the wedged workers
    (exactly the INC-54 enum worker), so we signal the session group started via
    start_new_session=True."""
    if p is None or p.poll() is not None:
        return
    try:
        pgid = os.getpgid(p.pid)
        os.killpg(pgid, signal.SIGTERM)
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass


def _install_signal_handlers() -> None:
    """On SIGTERM/SIGINT (systemd stop, Ctrl-C): kill the in-flight child group and
    RELEASE THE LOCK before dying. INC-54: without this, a stop leaves a stale lock
    (acquire_lock reclaims a dead-pid lock on the next start, but prompt release is
    cleaner and lets a same-second restart re-lock without the reclaim path)."""
    def _term(signum, _frame):
        log.info(f"signal {signum} -- killing child, releasing lock, exiting",
                 cat="runner", event="signal_exit")
        _kill_child_group(_CURRENT_CHILD)
        release_lock()
        os._exit(0)                       # cleanup already done; skip further loop code
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, _term)


# --------------------------------------------------------------------------- lock
def acquire_lock() -> bool:
    """Single-instance lock via _pidlock (atomic create + anchored holder match).

    Ultrareview PR #3 (2026-08-21): the previous in-file version matched ANY argv
    basename == forever_runner.py, so a recycled pid running `tail -f
    scripts/forever_runner.py` blocked the restart; main() returned 0 and
    Restart=on-failure then left the never-idle floor silently dead."""
    return acquire_pidlock(LOCK, "forever_runner.py",
                           lambda m: log.info(m, cat="runner"))


def release_lock() -> None:
    release_pidlock(LOCK)


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
def _effective_timeout_s(budget_h: float | None) -> float:
    """Wall cap in seconds: an explicit @budget_h wins (up OR down); otherwise the
    DEFAULT_MAX_WALL_H backstop so a wedge can never run unbounded (INC-54)."""
    h = budget_h if budget_h is not None else DEFAULT_MAX_WALL_H
    return h * 3600


def _run_campaign(args: list[str], budget_h: float | None, dry: bool) -> int:
    global _CURRENT_CHILD
    cmd = [sys.executable, str(REPO / "scripts" / "run_campaign.py"), *args]
    if dry:
        log.info(f"[dry-run] would run: {' '.join(args)}", cat="runner")
        return 0
    timeout = _effective_timeout_s(budget_h)
    # Own session/process-group so a timeout kill reaps the worker pool too, not just
    # the run_campaign parent (else the wedged enum worker is orphaned -- INC-54).
    p = subprocess.Popen(cmd, cwd=str(REPO), start_new_session=True)
    _CURRENT_CHILD = p
    try:
        return p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_child_group(p)
        if budget_h is not None:
            log.info(f"line hit budget_h={budget_h} -- moving on", cat="runner",
                     event="budget")
        else:
            log.error(f"WALL-CAP: no @budget_h and ran > {DEFAULT_MAX_WALL_H}h -- "
                      f"killed (likely hot-wedge, INC-54); moving on", cat="runner",
                      event="wall_cap")
        return 0                                  # capped stop = intended, not a failure loop
    finally:
        _CURRENT_CHILD = None


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
    d = REPO / "results" / "seeds" / FILLER_TREE / f"q{q}" / "p500_mt50" / f"n{n}_beta40"
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
    global WORKLIST, FILLER_CAMPAIGN, FILLER_CELLS, FILLER_WORKERS, FILLER_TREE
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="log decisions, spawn no campaigns; also caps the loop")
    ap.add_argument("--max-iters", type=int, default=0,
                    help="stop after N iterations (0 = forever; used by --dry-run/tests)")
    # Node-profile overrides (2026-08-23, steamdeck node): one shared runner, the
    # unit file picks the worklist and filler for its box. Defaults unchanged =
    # the workstation profile.
    ap.add_argument("--worklist", default=None, metavar="PATH",
                    help="alternate worklist file, relative to the repo root "
                         "(default config/forever_worklist.txt)")
    ap.add_argument("--filler-campaign", default=None, metavar="NAME",
                    help=f"idle-filler campaign (default {FILLER_CAMPAIGN})")
    ap.add_argument("--filler-cells", default=None, metavar="N:Q[,N:Q...]",
                    help="idle-filler frontier cells (default "
                         + ",".join(f"{n}:{q}" for n, q in FILLER_CELLS) + ")")
    ap.add_argument("--filler-workers", type=int, default=None,
                    help=f"idle-filler --workers (default {FILLER_WORKERS})")
    ap.add_argument("--filler-tree", default=None, metavar="TREE",
                    help="seed tree the filler campaign writes (its seed_tag; "
                         f"default {FILLER_TREE}) — where cell seeds are counted")
    args = ap.parse_args(argv)
    if args.worklist:
        WORKLIST = Path(args.worklist) if os.path.isabs(args.worklist) else REPO / args.worklist
    if args.filler_campaign:
        FILLER_CAMPAIGN = args.filler_campaign
    if args.filler_workers:
        FILLER_WORKERS = args.filler_workers
    if args.filler_tree:
        FILLER_TREE = args.filler_tree
    if args.filler_cells:
        try:
            FILLER_CELLS = [(int(n), int(q)) for n, q in
                            (c.split(":") for c in args.filler_cells.split(","))]
        except ValueError:
            ap.error(f"--filler-cells must be N:Q[,N:Q...], got {args.filler_cells!r}")
    if args.dry_run:
        os.environ["PIPELINE_LOG_TAG"] = "dryrun"   # central log, marked synthetic

    if not args.dry_run and not acquire_lock():
        return 3                                 # non-zero: Restart=on-failure retries, status shows it
    if not args.dry_run:
        _install_signal_handlers()               # release lock + kill child on stop (INC-54)
    consec_fail = 0
    it = 0
    try:
        log.info(f"==== forever_runner up ==== worklist={WORKLIST.name} "
                 f"filler={FILLER_CAMPAIGN} tree={FILLER_TREE} "
                 f"workers={FILLER_WORKERS} cells={FILLER_CELLS}", cat="runner")
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
