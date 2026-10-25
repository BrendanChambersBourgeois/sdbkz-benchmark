"""_ntru_seed_worker task-tuple guard.

Only the two builders' shapes are legal: run_packed's 9 fields (the tail takes
_NTRU_TASK_TAIL_DEFAULTS) and run_campaign main's 13. A 10-12 field tuple used
to take tail defaults silently; it now raises before any import or file access.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import run_campaign as rc  # noqa: E402

_HEAD = (17, 10, 7, 3329, 53, 1, "ntru", "ntru_test", "fplll")
_TAIL = ("long double", True, True, True)


class _Captured(BaseException):
    """Escapes the worker's `except Exception`: no seed JSON, no log line."""


@pytest.mark.parametrize("k", [8, 10, 11, 12, 14])
def test_malformed_length_raises(k):
    task = (_HEAD + _TAIL + ("extra",))[:k]
    with pytest.raises(ValueError, match="want 9 or 13"):
        rc._ntru_seed_worker(task)


@pytest.mark.parametrize("task, tail", [
    (_HEAD, rc._NTRU_TASK_TAIL_DEFAULTS),  # run_packed.build_tasks shape
    (_HEAD + _TAIL, _TAIL),                # run_campaign.main shape
])
def test_valid_lengths_pad_as_before(task, tail, tmp_path, monkeypatch):
    import _bkz_core
    import _seed_paths
    seen = {}

    def _fake_run_single(**kw):
        seen.update(kw)
        raise _Captured

    out = tmp_path / "seed.json"
    monkeypatch.setattr(_seed_paths, "seed_path_for", lambda *a, **kw: str(out))
    monkeypatch.setattr(_bkz_core, "run_single", _fake_run_single)
    with pytest.raises(_Captured):
        rc._ntru_seed_worker(task)
    assert (seen["metric_float_type"], seen["store_short_vectors"],
            seen["store_per_tour"], seen["sieve_trace"]) == tail
    assert not out.exists()
