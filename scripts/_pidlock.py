"""Single-instance pid lock shared by the long-running drivers.

History (why both halves matter -- ultrareview PR #3, 2026-08-21):
  * forever_runner.py had the ATOMIC create (O_CREAT|O_EXCL) but a LOOSE holder
    match (any argv basename == script), so a SIGKILL-orphaned lock whose pid was
    recycled to `tail -f scripts/forever_runner.py` blocked the restart; with
    main() returning 0 and Restart=on-failure the never-idle floor died silently.
  * onset_driver.py had the ANCHORED match (python interpreter running the
    script -- audit #4 2026-07-05) but a non-atomic exists()->write_text(), so
    two racers could both pass the check and both "hold" the lock.
One helper, both properties:
  * create is atomic: the pid is written to a private temp file which is then
    hard-linked to the lock path (link(2) fails with EEXIST if the lock exists),
    so a concurrent reader never observes an empty/partial lock file;
  * a holder is live only if its pid is alive AND /proc/<pid>/cmdline is a python
    interpreter running `script_basename`; anything else (dead pid, recycled pid,
    unparseable file) is reclaimed by unlink + retry of the atomic create, so two
    simultaneous reclaimers resolve to exactly one holder.
"""
from __future__ import annotations

import errno
import os
from collections.abc import Callable
from pathlib import Path

_MAX_ATTEMPTS = 5


def _holder_is_live(lock: Path, script_basename: str) -> bool:
    """True iff the pid in `lock` is alive and is a python running script_basename."""
    try:
        old = int(lock.read_text().strip())
    except (ValueError, FileNotFoundError, OSError):
        return False                         # empty/garbage/vanished -> not a holder
    try:
        os.kill(old, 0)
    except ProcessLookupError:
        return False                         # dead pid
    except PermissionError:
        pass                                 # alive, foreign user -- check cmdline
    except OSError:
        return False
    try:
        argv = (Path(f"/proc/{old}/cmdline").read_bytes()
                .decode(errors="replace").split("\0"))
    except OSError:
        return False
    # Anchored: interpreter basename contains "python" AND some argv entry IS the
    # script. `tail -f scripts/X.py`, `vim X.py`, `pytest tests/test_X.py` all fail.
    return bool(argv) and "python" in os.path.basename(argv[0]) \
        and any(os.path.basename(a) == script_basename for a in argv)


def _try_create(lock: Path, pid: int) -> bool:
    """Atomically create `lock` containing `pid`. False if it already exists."""
    tmp = lock.with_name(f".{lock.name}.{pid}.tmp")
    try:
        tmp.write_text(str(pid))
        try:
            os.link(tmp, lock)               # atomic create-with-content
            return True
        except FileExistsError:
            return False
        except OSError as e:
            if e.errno not in (errno.EPERM, errno.ENOTSUP, errno.EXDEV, errno.EOPNOTSUPP):
                raise
            # filesystem without hard links: fall back to exclusive create + write
            try:
                fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                return False
            os.write(fd, str(pid).encode())
            os.close(fd)
            return True
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def acquire_pidlock(lock: Path, script_basename: str,
                    log: Callable[[str], None]) -> bool:
    """Take `lock` for this process. Returns False if a live instance holds it."""
    lock.parent.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    for _ in range(_MAX_ATTEMPTS):
        if _try_create(lock, pid):
            return True
        if _holder_is_live(lock, script_basename):
            log(f"another {script_basename} holds the lock -- exiting")
            return False
        log("stale/foreign lock -- reclaiming")
        try:
            lock.unlink()
        except FileNotFoundError:
            pass                             # a concurrent reclaimer got there first
    log(f"could not acquire lock after {_MAX_ATTEMPTS} attempts -- exiting")
    return False


def release_pidlock(lock: Path) -> None:
    """Remove `lock` iff this process owns it."""
    try:
        if lock.exists() and int(lock.read_text().strip()) == os.getpid():
            lock.unlink()
    except (ValueError, FileNotFoundError, OSError):
        pass
