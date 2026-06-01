"""Unit tests for scripts/_signal_utils.managed_pool.

Synthetic-only: never spawns a real worker pool with imap_unordered
against BKZ code. Verifies the context manager installs SIGINT +
SIGTERM handlers on entry, restores them on exit, and best-effort-
terminates the underlying Pool. Signal-handler bodies are not
invoked directly here — the contract under test is registration,
restoration, and cleanup, not signal-fire behaviour itself.
"""
from __future__ import annotations

import os
import signal
import sys
from unittest import mock

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import _signal_utils  # noqa: E402


def test_managed_pool_yields_pool_object():
    with _signal_utils.managed_pool(processes=1, label="test") as pool:
        assert pool is not None
        # Pool object has standard multiprocessing.Pool API surface.
        assert hasattr(pool, "imap_unordered")
        assert hasattr(pool, "terminate")
        assert hasattr(pool, "close")


def test_managed_pool_installs_sigint_sigterm_handlers():
    prev_int = signal.getsignal(signal.SIGINT)
    prev_term = signal.getsignal(signal.SIGTERM)

    with _signal_utils.managed_pool(processes=1, label="test") as _pool:
        inside_int = signal.getsignal(signal.SIGINT)
        inside_term = signal.getsignal(signal.SIGTERM)
        assert inside_int is not prev_int
        assert inside_term is not prev_term

    # On exit, the prior handlers must be restored exactly.
    assert signal.getsignal(signal.SIGINT) is prev_int
    assert signal.getsignal(signal.SIGTERM) is prev_term


def test_managed_pool_terminates_on_clean_exit():
    # The cleanup path calls pool.terminate() + pool.join() even on
    # the clean-exit branch (workers are already drained at this
    # point so terminate is a no-op for in-flight state).
    with mock.patch("_signal_utils.Pool") as PoolCls:
        instance = mock.MagicMock()
        PoolCls.return_value = instance
        with _signal_utils.managed_pool(processes=1, label="test") as pool:
            assert pool is instance
        instance.terminate.assert_called()
        instance.join.assert_called()


def test_managed_pool_swallows_terminate_failure_on_exit():
    # If pool.terminate() raises (e.g. workers already dead), the
    # context manager must still exit cleanly and not propagate.
    with mock.patch("_signal_utils.Pool") as PoolCls:
        instance = mock.MagicMock()
        instance.terminate.side_effect = RuntimeError("dead workers")
        PoolCls.return_value = instance
        # Should not raise.
        with _signal_utils.managed_pool(processes=1, label="test") as pool:
            assert pool is instance


def test_managed_pool_restores_handlers_even_on_inner_exception():
    prev_int = signal.getsignal(signal.SIGINT)
    prev_term = signal.getsignal(signal.SIGTERM)

    with pytest.raises(RuntimeError, match="inner blew up"):
        with _signal_utils.managed_pool(processes=1, label="test"):
            raise RuntimeError("inner blew up")

    assert signal.getsignal(signal.SIGINT) is prev_int
    assert signal.getsignal(signal.SIGTERM) is prev_term


def test_managed_pool_label_passed_through():
    # `label` is keyword-only (per managed_pool signature) and must
    # not be forwarded to Pool(). The Pool constructor never sees it.
    with mock.patch("_signal_utils.Pool") as PoolCls:
        PoolCls.return_value = mock.MagicMock()
        with _signal_utils.managed_pool(processes=4, label="custom-label"):
            pass
        call_kwargs = PoolCls.call_args.kwargs
        assert "label" not in call_kwargs
        assert call_kwargs.get("processes") == 4


def _capture_handler():
    """Helper: return the SIGINT handler installed by managed_pool.

    The handler is a closure over Pool / aborted / label / time /
    PIPELINE so it can only be reached through the context manager
    that installed it. We use a one-shot context that captures the
    registered handler and the underlying mocked Pool before exiting.
    """
    captured = {}
    with mock.patch("_signal_utils.Pool") as PoolCls:
        pool_instance = mock.MagicMock()
        PoolCls.return_value = pool_instance
        with _signal_utils.managed_pool(processes=1, label="sig-test"):
            captured["handler"] = signal.getsignal(signal.SIGINT)
            captured["pool"] = pool_instance
    return captured


def test_signal_handler_first_invocation_terminates_and_exits():
    cap = _capture_handler()
    handler = cap["handler"]
    pool = cap["pool"]

    # Patch sys.exit to raise SystemExit (its default behaviour); also
    # neutralise os._exit so a second-signal path (not exercised here)
    # can't kill the pytest process.
    with mock.patch.object(_signal_utils, "time") as tmod, \
         mock.patch("_signal_utils.os._exit") as os_exit:
        tmod.sleep.return_value = None
        with pytest.raises(SystemExit) as exc_info:
            handler(signal.SIGINT, None)

    # POSIX convention: 128 + signum.
    assert exc_info.value.code == 128 + int(signal.SIGINT)
    pool.terminate.assert_called()
    pool.join.assert_called()
    os_exit.assert_not_called()


def test_signal_handler_second_invocation_calls_os_exit():
    cap = _capture_handler()
    handler = cap["handler"]

    # First call: SystemExit branch (covered by previous test). Second
    # call hits the os._exit hard-exit branch.
    with mock.patch.object(_signal_utils, "time") as tmod, \
         mock.patch("_signal_utils.os._exit") as os_exit:
        tmod.sleep.return_value = None
        with pytest.raises(SystemExit):
            handler(signal.SIGINT, None)
        # Second call — must invoke os._exit instead of going through
        # sys.exit again.
        handler(signal.SIGTERM, None)

    os_exit.assert_called_once_with(128 + int(signal.SIGTERM))


def test_signal_handler_swallows_pool_terminate_failure_during_signal():
    cap = _capture_handler()
    handler = cap["handler"]
    pool = cap["pool"]
    pool.terminate.side_effect = RuntimeError("workers gone")

    with mock.patch.object(_signal_utils, "time") as tmod, \
         mock.patch("_signal_utils.os._exit"):
        tmod.sleep.return_value = None
        # Even with a terminate failure, the handler must still
        # complete via sys.exit (raised as SystemExit).
        with pytest.raises(SystemExit):
            handler(signal.SIGINT, None)
