"""Graceful Pool shutdown on SIGINT / SIGTERM for sweep-style runners.

Without an explicit handler, Ctrl-C inside a `with Pool(...) as pool:`
block during a long imap_unordered loop leaves zombie worker
processes, partially-written seed JSONs, and no record of the abort
in pipeline.jsonl. This module provides a `managed_pool` context
manager that:

  - Installs SIGINT + SIGTERM handlers on entry.
  - Logs the abort to pipeline.jsonl as WARNING (cat="signal") with
    the run_id so analysis can find it.
  - Calls pool.terminate() + pool.join() with a small grace window
    so any in-flight worker finishes its current write or aborts
    cleanly.
  - Restores the previous handlers on exit (so a wrapper that calls
    multiple Pools sequentially keeps working).
  - Exits with code 130 (SIGINT) or 143 (SIGTERM) per POSIX
    convention so external watchdogs can distinguish abort-by-signal
    from crash-by-exception.

Usage:

    from _signal_utils import managed_pool

    with managed_pool(processes=22, maxtasksperchild=1,
                      label="cliff_500bit") as pool:
        for r in pool.imap_unordered(worker, todo):
            ...

Thin wrapper around multiprocessing.Pool — every Pool kwarg is
passed through unchanged.
"""
from __future__ import annotations

import os
import signal
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from multiprocessing import Pool
from multiprocessing.pool import Pool as PoolT
from types import FrameType
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from log import get_logger  # noqa: E402

PIPELINE = get_logger("_signal_utils")

# Grace window between Pool.terminate() and Pool.join() so a worker
# in the middle of a JSON dump can finish flushing.
TERMINATE_GRACE_S: float = 2.0


@contextmanager
def managed_pool(
    *pool_args: Any,
    label: str = "pool",
    **pool_kwargs: Any,
) -> Iterator[PoolT]:
    """Context manager: Pool with SIGINT / SIGTERM handling.

    `label` shows up in the abort log message; pass the runner's
    name (e.g. "cliff_500bit") for easy correlation.
    """
    pool = Pool(*pool_args, **pool_kwargs)
    aborted: dict[str, Optional[int]] = {"signal": None}

    def _handler(signum: int, frame: Optional[FrameType]) -> None:
        if aborted["signal"] is not None:
            # Second signal — escalate to immediate exit. The
            # explicit return after os._exit defends against mocked
            # os._exit in tests (real os._exit doesn't return).
            print(f"\n  {label}: second signal received, hard-exiting",
                  flush=True)
            os._exit(128 + signum)
            return
        aborted["signal"] = signum
        sig_name = signal.Signals(signum).name
        print(f"\n  {label}: {sig_name} received, terminating pool "
              f"(grace {TERMINATE_GRACE_S}s)...", flush=True)
        PIPELINE.warning(
            f"{label} aborted by signal", cat="signal",
            signal=sig_name, signum=signum, label=label,
        )
        try:
            pool.terminate()
            time.sleep(TERMINATE_GRACE_S)
            pool.join()
        except Exception:
            pass
        # Standard POSIX exit code: 128 + signum
        sys.exit(128 + signum)

    old_int = signal.signal(signal.SIGINT, _handler)
    old_term = signal.signal(signal.SIGTERM, _handler)
    try:
        yield pool
    finally:
        # Restore previous handlers so subsequent Pool blocks (or
        # the parent process) retain their own signal disposition.
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
        # Best-effort cleanup. We use terminate() (not close()) even on
        # the clean-exit path because:
        #   - Callers drain the full imap_unordered iterator before
        #     leaving the context — by the time we're here, workers
        #     are idle and terminate() is a no-op for in-flight state.
        #   - If the user raised inside the context (e.g. a pickle
        #     failure on args), pool.close() + pool.join() would hang
        #     forever waiting for dead workers. terminate() guarantees
        #     progress.
        try:
            pool.terminate()
            pool.join()
        except Exception:
            pass
