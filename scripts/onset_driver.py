#!/usr/bin/env python3
"""Adaptive NTRU DSD-onset boundary driver (long-running, unattended).

Traces the q*(n) onset curve for a FIXED practical reduction (BKZ beta, max_tours,
precision are the OBJECT of study, held constant) using the cancellation-free
secret-recovery readout (``secret_recovered_*`` from exact integer basis norms;
independent of the fpylll GSO -345 cancellation sentinel). For each n it hunts q
upward from a low multiple of the fatigue line q_fat(n)=0.004*n^2.484 and does one
of three things per cell verdict:

  * CRACK  -> bisect down to bracket the onset q*(n), then advance to the next n.
  * NULL, ratio still FALLING with q (cliff approaching) -> keep hunting up.
  * NULL, ratio PLATEAUED high (beta-wall signature) -> declare wall, advance.

The plateau test is the key economy vs a naive climb-to-QCAP: n>=173 saturate at a
best-vector ratio ~40-58x the planted secret and stop responding to q, so climbing
further only burns compute confirming a wall we can already call. (Learned from the
n=173/n=181 nulls vs the n=157 clean cliff; adversarial review wf_cfda0614-d38.)

Pure orchestration over the committed ``ntru_onset_boundary`` campaign + --n/--q
overrides. Resumable: reads completed cells off disk and skips them, so it is safe
to relaunch after a crash or reboot (a lockfile prevents a double-launch). Runs one
20-worker cell at a time -- no core contention.

Usage:
    python3 scripts/onset_driver.py                 # default month-long ladder
    python3 scripts/onset_driver.py --budget-h 24   # short window
    python3 scripts/onset_driver.py --ladder 167 163 179   # explicit n order
    python3 scripts/onset_driver.py --dry-run       # plan only, spawn nothing
"""
import argparse
import glob
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from _config import ConfigError, load_campaign  # noqa: E402
from log import get_logger, new_run_id  # noqa: E402

PIPELINE = get_logger("onset_driver")

# --- fixed reduction under study (the b40/mt50/p500 spec) --------------------
BETA, P, MT, SEEDS, WORKERS = 40, 500, 50, 20, 20
CAMPAIGN = "ntru_onset_boundary"

# --- search shape (x q_fat) --------------------------------------------------
START_MULT = 2.0     # first probe: intermediate-n onset sits near n=157's ~1.9x
STEP_MULT = 0.30     # q step while hunting the first crack
TOL_MULT = 0.12      # stop bisecting once (crack-null)/q_fat <= this
QCAP_MULT = 5.0      # hard backstop; the ratio-plateau test usually fires first
CELL_TIMEOUT_H = 40  # kill+skip a cell exceeding this (hang guard); >> any real
                     #   cell (largest observed ~19h at n=181 high q)
CELL_ATTEMPTS = 2    # run a failing/stalled cell this many times total before
                     #   abandoning the n (bounded retry: survivors on disk skip,
                     #   so attempt 2 only reruns the missing seeds). Replaces the
                     #   old raise-CellFailure-and-exit path, which let ONE
                     #   unwritable seed restart-loop the service into systemd's
                     #   StartLimitBurst and silently kill the month run
                     #   (audit 2026-07-04 #3, major 1).

# --- pool-stall watchdog ------------------------------------------------------
# A native worker crash (segfault/abort in fplll/MPFR) kills the pool worker
# without a Python exception; mp.Pool.imap_unordered then blocks forever and the
# only escape used to be the full CELL_TIMEOUT_H burn (audit 2026-07-04 #3,
# major 2). A live 20-worker cell accumulates ~1200 CPU-seconds per wall-minute;
# a hung pool accumulates ~0. Poll the child's process group and declare a stall
# when the group gains < STALL_CPU_S CPU-seconds over STALL_WINDOW_S of wall.
POLL_S = 60          # proc.poll()/CPU sample cadence
STALL_WINDOW_S = 30 * 60
STALL_CPU_S = 60.0

# --- post-bracket densification (the paper estimand needs it) -----------------
# Bisection converges on FIRST-CRACK from below and never probes q above it, but
# the reportable onset (extract_dsd_onset per-variant 50%-rate crossing) sits
# ABOVE first-crack (n=157: first-crack q2203 = SD 10%; SD 50% crossing ~q2354).
# Without graded-rate cells above first-crack the crossing cannot be
# interpolated (audit 2026-07-04 #3, major 5). After bracketing, keep stepping
# q upward in fine steps until both variants cross 50% or the cell budget runs
# out (BKZ lags SD and may stay unbracketed -- logged, acceptable).
DENSIFY_MAX = 3      # extra cells above the highest crack
DENSIFY_STEP = 0.10  # x q_fat -- finer than the hunt STEP_MULT
DENSIFY_TARGET = 0.5

# --- ratio-based wall detection ----------------------------------------------
# ratio r(cell) = min_seed( min(min_actual_norm2_bkz, _sdbkz) / secret_norm2 ).
# r <= 1.0  <=> a vector at least as short as the secret was found (a CRACK).
# A real beta-wall sits in a LOW SATURATED BAND (n=173 ~40-52x, n=181 ~56-58x):
# the basis stops shortening and parks tens-of-x above the secret. The PRE-cliff
# region is different -- the ratio falls monotonically through the THOUSANDS
# (n=157: 18488->1.00; n=181-low: 37868->46245->55519) before the cliff. So the
# wall test must require the ratio to have COLLAPSED INTO the band, not merely
# stopped falling while still huge -- else a rising pre-region false-walls one
# step below a real crack and never probes it (audit wf_8f1b8c57-b6e MUST-FIX #1).
WALL_LO = 10.0       # below this and it's essentially cracking
WALL_HI = 500.0      # above this the ratio is still in the falling pre-region
IMPROVE = 0.70       # "still falling" = newest r < IMPROVE * previous r (a cliff);
                     # otherwise the ratio has flattened -> beta-wall

# default ladder: the crack->wall transition lives between n=157 (crack ~1.9x) and
# n=173/181 (wall). 167 is live already; map its neighbours to pin the boundary.
# Extension (2026-07-15, workflow-picked): 173 self-verdicts as a beta-WALL on
# existing data (free bound, 0 new cells); 151/137/131/109 fill the steep rising
# leg for a gap-free onset-vs-dim curve. Resumable: relaunch skips completed cells.
# A relaunch re-opens 167/163 (their hunts never walled -> they climb toward QCAP);
# kept FIRST by user choice (2026-07-16 "let it ride") so the frontier upper-crack
# bound gets pinned before the gap-fills; 179 stays walled (skips); 149/139/127
# already bracketed; 173 walls free; gap-fills 151/137/131/109 run after.
DEFAULT_LADDER = [167, 163, 179, 149, 139, 127, 173, 151, 137, 131, 109]  # prime; nearest-boundary first

LOCK = REPO / "results" / "logs" / "onset_driver.lock"


def log(msg, **ctx):
    PIPELINE.info(msg, cat="onset_driver", **ctx)


def qfat(n):
    return 0.004 * n ** 2.484


def isprime(x):
    if x < 2:
        return False
    if x % 2 == 0:
        return x == 2
    i = 3
    while i * i <= x:
        if x % i == 0:
            return False
        i += 2
    return True


def nextprime(x):
    q = int(x) + 1
    while not isprime(q):
        q += 1
    return q


def prevprime(x):
    q = int(x) - 1
    while q > 2 and not isprime(q):
        q -= 1
    return q


def cell_dir(n, q):
    return REPO / f"results/seeds/ntru/q{q}/p{P}_mt{MT}/n{n}_beta{BETA}"


def _cell_seeds(n, q):
    return glob.glob(str(cell_dir(n, q) / "*.json"))


def verdict(n, q):
    """'CRACK' | 'NULL' | None (INCOMPLETE).

    CRACK = FIRST-CRACK of the cell (any one seed recovered, either oracle). This
    is a bisection-SEARCH signal ONLY -- it is NOT the paper's onset estimand.
    The reportable onset is the per-variant 50%-rate crossing computed by
    scripts/extract_dsd_onset.py; first-crack sits systematically lower (~3.4%
    quantile at N=20) and is not variant-attributable. Never put this q on a
    q*(n) trend axis (deep audit 2026-07-04, finding 4).

    INCOMPLETE (None) means: fewer than SEEDS files, OR any seed is not
    status=completed, OR any seed lacks BOTH recovery keys. Critically, an absent
    recovery key is treated as INCOMPLETE (re-run), never silently as NULL -- that
    was the bug in the throwaway tracer (missing key .get()->None->falsy->'NULL').
    """
    files = _cell_seeds(n, q)
    if len(files) < SEEDS:
        return None
    cracked = False
    for f in files:
        try:
            j = json.load(open(f))
        except Exception:
            return None
        if j.get("status") != "completed":
            return None
        has_bkz = "secret_recovered_bkz" in j
        has_sd = "secret_recovered_sdbkz" in j
        if not (has_bkz or has_sd):
            return None  # old-schema / missing readout -> re-run, do not call NULL
        if j.get("secret_recovered_bkz") or j.get("secret_recovered_sdbkz"):
            cracked = True
    return "CRACK" if cracked else "NULL"


def cell_ratio(n, q):
    """min over completed seeds of min(min_actual_norm2_{bkz,sdbkz})/secret_norm2.

    The continuous best-vector signal: ~1.0 = crack cliff, tens = beta-wall
    plateau. Returns None if the cell is incomplete or lacks the fields.
    """
    files = _cell_seeds(n, q)
    if len(files) < SEEDS:
        return None
    best = None
    for f in files:
        try:
            j = json.load(open(f))
        except Exception:
            return None
        sn = j.get("secret_norm2")
        if not sn:
            return None
        for k in ("min_actual_norm2_bkz", "min_actual_norm2_sdbkz"):
            v = j.get(k)
            if v is not None and v > 0:
                r = v / sn
                best = r if best is None else min(best, r)
    return best


def known(n):
    """{q: 'CRACK'|'NULL'} for every COMPLETE cell of this n on disk."""
    out = {}
    for d in glob.glob(str(REPO / f"results/seeds/ntru/q*/p{P}_mt{MT}/"
                             f"n{n}_beta{BETA}")):
        try:
            q = int(Path(d).parts[-3][1:])   # 'q4871' -> 4871
        except ValueError:
            continue
        v = verdict(n, q)
        if v:
            out[q] = v
    return out


def _kill_group(proc):
    """SIGTERM then SIGKILL the child's whole process group (the 20-worker pool
    orphans and keeps burning cores otherwise). Child is its own session leader."""
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _group_cpu(pid):
    """Cumulative CPU seconds of the child's whole process group (pool included),
    via `ps -o times`. None if unreadable (group already gone / ps failure)."""
    try:
        pgid = os.getpgid(pid)
        out = subprocess.run(["ps", "-g", str(pgid), "-o", "times="],
                             capture_output=True, text=True, timeout=30).stdout
        vals = [int(x) for x in out.split()]
        return float(sum(vals)) if vals else None
    except (ProcessLookupError, subprocess.TimeoutExpired, ValueError, OSError):
        return None


def _wait_with_watchdog(proc):
    """Wait for the cell child. Returns its int rc, or 'timeout' | 'stalled'.

    'stalled' = the child's process group gained < STALL_CPU_S CPU-seconds over
    STALL_WINDOW_S of wall clock -- the hung-pool signature (a segfaulted worker
    leaves imap_unordered blocked with ~0 CPU). Seed-file mtimes are NOT used:
    seeds flush clustered at the end of a cell, so hours of zero new files are
    normal while CPU keeps accumulating.
    """
    t0 = time.time()
    cpu_hi = 0.0
    fresh = time.time()
    while True:
        rc = proc.poll()
        if rc is not None:
            return rc
        if time.time() - t0 > CELL_TIMEOUT_H * 3600:
            return "timeout"
        cpu = _group_cpu(proc.pid)
        if cpu is not None and cpu > cpu_hi + STALL_CPU_S:
            cpu_hi = cpu
            fresh = time.time()
        if time.time() - fresh > STALL_WINDOW_S:
            return "stalled"
        time.sleep(POLL_S)


def _legacy_cell(n, q):
    """True if the cell is fully populated with parseable, completed seeds that
    ALL lack the recovery keys -- the pre-INC-51 schema (e.g. the published
    n=113 beta40 q569-859 Fig6 cells). Such a cell can never verdict: the seeds
    parse, so run_campaign's resume-skip keeps them, and re-running regenerates
    nothing. Detect it up front instead of burning CELL_ATTEMPTS on it
    (audit #4 2026-07-05)."""
    files = _cell_seeds(n, q)
    if len(files) < SEEDS:
        return False
    for f in files:
        try:
            j = json.load(open(f))
        except Exception:
            return False
        if j.get("status") != "completed":
            return False
        if "secret_recovered_bkz" in j or "secret_recovered_sdbkz" in j:
            return False
    return True


def run_cell(n, q, deadline, dry):
    """Run one cell to a verdict. Bounded retry: CELL_ATTEMPTS total, resuming
    from disk each time (existing complete seeds skip; run_campaign quarantines
    a corrupt seed JSON aside and regenerates it). Returns True on a verdict,
    False to abandon this n (deadline, or attempts exhausted) -- the ladder
    continues either way; the driver process never exits on a cell failure."""
    if time.time() >= deadline:
        log(f"DEADLINE hit -- skip n={n} q={q}")
        return False
    if verdict(n, q) is not None:
        log(f"n={n} q={q} already complete -- skip")
        return True
    if _legacy_cell(n, q):
        log(f"LEGACY n={n} q={q}: cell complete on the pre-recovery-key schema "
            f"-- cannot verdict and re-running regenerates nothing; abandoning "
            f"n={n} (published data untouched; drop this n from the ladder)",
            n=n, q=q, event="legacy_cell")
        return False
    mult = round(q / qfat(n), 3)
    log(f"START n={n} q={q} ({mult}x q_fat)", n=n, q=q, mult=mult)
    if dry:
        log(f"[dry-run] would run campaign {CAMPAIGN} --n {n} --q {q}")
        return True
    for attempt in range(1, CELL_ATTEMPTS + 1):
        # child run_campaign emits its own structured records to pipeline.jsonl;
        # drop console stdout, keep stderr (inherited) for crashes.
        # start_new_session so a hung cell's whole pool dies as a group.
        proc = subprocess.Popen(
            ["python3", "scripts/run_campaign.py", "--campaign", CAMPAIGN,
             "--n", str(n), "--q", str(q), "--workers", str(WORKERS)],
            cwd=REPO, stdout=subprocess.DEVNULL, start_new_session=True,
        )
        rc = _wait_with_watchdog(proc)
        if rc in ("timeout", "stalled"):
            log(f"{rc.upper()} n={n} q={q} attempt {attempt}/{CELL_ATTEMPTS} "
                f"-- killing worker group", n=n, q=q, event=rc, attempt=attempt)
            _kill_group(proc)
            continue
        v = verdict(n, q)
        if rc == 0 and v is not None:
            r = cell_ratio(n, q)
            log(f"DONE  n={n} q={q} -> {v} (ratio={r:.2f})" if r else
                f"DONE  n={n} q={q} -> {v}", n=n, q=q, verdict=v,
                ratio=round(r, 3) if r else None)
            return True
        log(f"FAIL  n={n} q={q} attempt {attempt}/{CELL_ATTEMPTS}: "
            f"run_campaign rc={rc}, verdict={v} -- cell did not complete",
            n=n, q=q, rc=rc, event="cell_fail", attempt=attempt)
    log(f"GIVE UP n={n} q={q} after {CELL_ATTEMPTS} attempts -- abandoning n={n}, "
        f"ladder continues", n=n, q=q, event="cell_abandoned")
    return False


def _wall_reached(n, nulls):
    """True if the NULL ratios have settled in the saturated band => beta-wall.

    Needs >=2 completed NULL cells. The highest-q null ratio must (a) have stopped
    falling like a cliff (r_last >= IMPROVE*r_prev) AND (b) sit inside the low
    saturated wall band WALL_LO < r_last < WALL_HI. Condition (b) is what stops a
    RISING pre-cliff region (ratios in the thousands) from being mistaken for a
    wall and skipping a crack one step higher -- see WALL_LO/WALL_HI note above.
    """
    if len(nulls) < 2:
        return False
    ratios = [(q, cell_ratio(n, q)) for q in nulls]
    ratios = [(q, r) for q, r in ratios if r is not None]
    if len(ratios) < 2:
        return False
    ratios.sort()                       # by q ascending
    (_, r_prev), (_, r_last) = ratios[-2], ratios[-1]
    plateau = r_last >= IMPROVE * r_prev          # failed to fall like a cliff
    return plateau and WALL_LO < r_last < WALL_HI  # settled in the saturated band


def _variant_rates(n, q):
    """(bkz_rate, sdbkz_rate) over the cell's seeds, or None if incomplete."""
    files = _cell_seeds(n, q)
    if len(files) < SEEDS:
        return None
    cb = cs = 0
    for f in files:
        try:
            j = json.load(open(f))
        except Exception:
            return None
        cb += bool(j.get("secret_recovered_bkz"))
        cs += bool(j.get("secret_recovered_sdbkz"))
    return cb / len(files), cs / len(files)


def _densify(n, deadline, dry):
    """Fill graded-rate cells ABOVE the first-crack so the paper estimand (the
    per-variant 50%-rate crossing, scripts/extract_dsd_onset.py) is
    interpolatable. Bisection alone never probes q > first-crack, but the 50%
    crossing sits above it (see DENSIFY_* note). Steps q upward in
    DENSIFY_STEP*q_fat increments until both variants reach DENSIFY_TARGET or
    DENSIFY_MAX cells are spent; a still-unbracketed BKZ crossing is logged and
    left to a manual follow-up (BKZ lags SD by design of the phenomenon)."""
    k = known(n)
    cracks = sorted(q for q, v in k.items() if v == "CRACK")
    if not cracks:
        return
    qf = qfat(n)
    q = cracks[-1]
    for _ in range(DENSIFY_MAX):
        rates = _variant_rates(n, q)
        if rates and min(rates) >= DENSIFY_TARGET:
            log(f"n={n}: densify done -- both variants >= "
                f"{DENSIFY_TARGET:.0%} at q={q} (bkz={rates[0]:.0%}, "
                f"sd={rates[1]:.0%})", n=n, event="densify_done")
            return
        nq = nextprime(q + DENSIFY_STEP * qf)
        if nq > qf * QCAP_MULT:
            log(f"n={n}: densify hit QCAP at q={nq} -- stopping", n=n)
            return
        if not run_cell(n, nq, deadline, dry):
            return
        q = nq
    rates = _variant_rates(n, q)
    log(f"n={n}: densify budget spent at q={q} "
        f"(bkz={rates[0]:.0%}, sd={rates[1]:.0%})" if rates else
        f"n={n}: densify budget spent at q={q}",
        n=n, event="densify_budget")


def trace_n(n, deadline, dry, push_wall=False):
    qf = qfat(n)
    tol = TOL_MULT * qf
    tried = set()
    while time.time() < deadline:
        k = known(n)
        cracks = sorted(q for q, v in k.items() if v == "CRACK")
        nulls = sorted(q for q, v in k.items() if v == "NULL")
        if not cracks:
            if push_wall and _wall_reached(n, nulls):
                log(f"n={n}: wall band reached but --push-walls set -- "
                    f"climbing past q={max(nulls)} ({max(nulls)/qf:.2f}x q_fat) "
                    f"toward QCAP {QCAP_MULT}x", n=n, event="push_wall")
            elif _wall_reached(n, nulls):
                r = cell_ratio(n, max(nulls))
                log(f"n={n}: beta-WALL -- NULL ratio plateaued at {r:.1f}x secret "
                    f"through q={max(nulls)} ({max(nulls)/qf:.2f}x q_fat); "
                    f"no q cracks. advancing", n=n)
                return
            base = max(nulls) if nulls else int(qf * START_MULT)
            nq = nextprime(base + STEP_MULT * qf) if nulls \
                else nextprime(int(qf * START_MULT))
            if nq > qf * QCAP_MULT:
                log(f"n={n}: NULL up to {nq} (> {QCAP_MULT}x q_fat) -- "
                    f"QCAP backstop, no onset; advancing", n=n)
                return
        else:
            lc = cracks[0]
            lower_nulls = [q for q in nulls if q < lc]
            if lower_nulls:
                hn = max(lower_nulls)
                if lc - hn <= tol:
                    log(f"n={n}: q*({n}) BRACKETED ({hn} null, {lc} crack] "
                        f"~ {lc/qf:.2f}x q_fat -- densifying for the 50% "
                        f"crossing", n=n, q_star_mult=round(lc / qf, 3))
                    _densify(n, deadline, dry)
                    return
                nq = nextprime((hn + lc) // 2)
                if nq <= hn or nq >= lc:
                    log(f"n={n}: bisect converged at prime gap ({hn},{lc}) "
                        f"~ {lc/qf:.2f}x -- densifying for the 50% crossing",
                        n=n, q_star_mult=round(lc / qf, 3))
                    _densify(n, deadline, dry)
                    return
            else:
                nq = prevprime(int(lc - STEP_MULT * qf))
                if nq <= qf:
                    log(f"n={n}: crack down to ~q_fat -- onset ~ {lc/qf:.2f}x; "
                        f"densifying for the 50% crossing", n=n)
                    _densify(n, deadline, dry)
                    return
        if nq in tried:
            log(f"n={n}: next q={nq} already attempted this run -- stop", n=n)
            return
        tried.add(nq)
        if not run_cell(n, nq, deadline, dry):
            return


def _acquire_lock():
    """Refuse to start if another driver is live (prevents cron@reboot double-run).

    Stale lock (pid dead) is reclaimed. A live pid whose /proc cmdline is NOT an
    onset_driver is a REUSED pid (SIGKILL left the lock; the pid was recycled) --
    reclaimed too, else the month run silently never restarts (audit 2026-07-04
    #3, minor 6). Returns True on success.
    """
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            old = int(LOCK.read_text().strip())
        except ValueError:
            old = None
            log("unparseable lock -- reclaiming")
        if old is not None:
            alive = True
            try:
                os.kill(old, 0)          # raises if pid gone
            except ProcessLookupError:
                alive = False
                log("stale lock found -- reclaiming")
            except PermissionError:
                pass                     # alive, foreign user -- check cmdline
            if alive:
                try:
                    argv = Path(f"/proc/{old}/cmdline").read_bytes() \
                        .decode(errors="replace").split("\0")
                except OSError:
                    argv = []
                # Anchored match: a python interpreter running THIS script.
                # A loose "onset_driver in cmdline" substring false-blocks on
                # a recycled pid running e.g. `tail -f scripts/onset_driver.py`
                # or `pytest tests/test_onset_driver.py` (audit #4 2026-07-05;
                # basename of test_onset_driver.py does not match).
                is_driver = argv and "python" in os.path.basename(argv[0]) \
                    and any(os.path.basename(a) == "onset_driver.py"
                            for a in argv)
                if is_driver:
                    log(f"another onset_driver (pid {old}) holds the lock "
                        f"-- exiting")
                    return False
                log(f"lock pid {old} alive but not an onset_driver "
                    f"(pid reuse) -- reclaiming")
    LOCK.write_text(str(os.getpid()))
    return True


def _check_campaign():
    """Assert the committed campaign's fixed knobs match this driver's constants.

    The driver hardcodes P/MT/SEEDS/BETA to build the on-disk cell paths and the
    verdict counts; if someone edits config/sweep.toml (e.g. precision->1000) the
    child would write to p1000_mt50 and every cell this driver looks for would be
    silently orphaned. Fail loudly at startup instead (audit should-fix).
    """
    try:
        c = load_campaign(CAMPAIGN)
    except ConfigError as e:
        print(f"ERROR: cannot load campaign {CAMPAIGN!r}: {e}", file=sys.stderr)
        return False
    mismatch = []
    if c.precision != P:
        mismatch.append(f"precision {c.precision} != {P}")
    if c.num_seeds != SEEDS:
        mismatch.append(f"num_seeds {c.num_seeds} != {SEEDS}")
    if BETA not in c.beta_grid:
        mismatch.append(f"beta {BETA} not in beta_grid {c.beta_grid}")
    if c.tours_by_beta.get(BETA) != MT:
        mismatch.append(f"tours_by_beta[{BETA}] {c.tours_by_beta.get(BETA)} != {MT}")
    if mismatch:
        print(f"ERROR: campaign {CAMPAIGN!r} drifted from driver constants: "
              f"{'; '.join(mismatch)}", file=sys.stderr)
        return False
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ladder", type=int, nargs="+", default=DEFAULT_LADDER,
                    help="n values to trace, in order (all must be prime)")
    ap.add_argument("--budget-h", type=float, default=30 * 24,
                    help="wallclock budget in hours (default 720 = 30 days)")
    ap.add_argument("--push-walls", type=int, nargs="+", default=[],
                    metavar="N",
                    help="dims for which to IGNORE the beta-wall early-stop and "
                         "keep climbing q to the QCAP backstop (5x q_fat). For "
                         "re-sampling a dim that was declared walled on too few "
                         "low-q cells -- e.g. n=173 (only sampled to 2.81x).")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan and log decisions but spawn no campaigns")
    args = ap.parse_args(argv)
    if args.dry_run:
        os.environ["PIPELINE_LOG_TAG"] = "dryrun"   # central log, marked synthetic

    bad = [n for n in args.ladder if not isprime(n)]
    if bad:
        print(f"ERROR: non-prime n in ladder: {bad} (NTRU needs prime n)",
              file=sys.stderr)
        return 2
    # our cell paths write/read n{n} unpadded; the seed-path helper zero-pads
    # n<100 (n{n:03d}), so a two-digit n would silently orphan every cell.
    low = [n for n in args.ladder if n < 100]
    if low:
        print(f"ERROR: n<100 not supported (path padding mismatch): {low}",
              file=sys.stderr)
        return 2
    stray = [n for n in args.push_walls if n not in args.ladder]
    if stray:
        print(f"ERROR: --push-walls dims not in ladder: {stray}",
              file=sys.stderr)
        return 2

    if not _check_campaign():
        return 2

    if not args.dry_run and not _acquire_lock():
        return 0
    try:
        new_run_id()
        deadline = time.time() + args.budget_h * 3600
        log(f"==== onset_driver up. ladder={args.ladder} budget={args.budget_h}h "
            f"deadline={time.strftime('%F %T', time.localtime(deadline))} "
            f"dry_run={args.dry_run} ====")
        for n in args.ladder:
            if time.time() >= deadline:
                log("DEADLINE -- stopping before next n")
                break
            log(f"---- tracing n={n} (q_fat~{qfat(n):.0f}) ----", n=n)
            trace_n(n, deadline, args.dry_run, push_wall=(n in args.push_walls))
        log("==== onset_driver complete or deadline ====")
    finally:
        if not args.dry_run and LOCK.exists():
            try:
                if int(LOCK.read_text().strip()) == os.getpid():
                    LOCK.unlink()
            except (ValueError, FileNotFoundError):
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
