#!/usr/bin/env python3
"""Unit test for the Phase 4a `_log_clamp` wrapper swap.

Verifies that each legacy `_log_clamp` / `_log_clamp_cloud` wrapper in
the seven sweep scripts emits the same JSONL schema as the paper
baseline pre-swap code. The log body schema is a reproducibility
contract (clamp_events.jsonl is committed data), so the swap must not
change any field.

For each script, this test:
  1. Imports the module (with argv-mocking for scripts that parse
     argparse at import time).
  2. Calls the wrapper with a fixed (ctx, position, raw_value) triple,
     redirecting the log_path to a temp file.
  3. Reads back the written JSONL line, asserts the required fields
     are present, the `script` field matches the expected name, and
     the numeric fields round-trip losslessly.

Does not hit the main-sweep numerical path — that is covered by
verify.sh + test_math_core_parity.py. This is strictly a
log-schema regression guard for Phase 4a.

Usage: python3 scripts/test_log_clamp_wrappers.py
"""
import json
import os
import sys
import tempfile
from unittest.mock import patch

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

from log import get_logger  # noqa: E402
PIPELINE = get_logger("test_log_clamp_wrappers")

# Pre-import modules via argv-mock so argparse doesn't choke.
_saved = sys.argv
sys.argv = ["dummy.py"]
import sweep_parallel  # noqa: E402
import sweep_cloud  # noqa: E402
import overnight_experiments  # noqa: E402
import run_3x_extended  # noqa: E402
import run_convergence_test  # noqa: E402
sys.argv = ["q3329_verify.py", "--n", "100", "--beta", "30",
            "--seeds", "1", "--precision", "250"]
import q3329_verify  # noqa: E402
sys.argv = _saved

WRAPPERS = [
    # (module, wrapper_fn, expected_script_name)
    (sweep_parallel, sweep_parallel._log_clamp, "sweep_parallel"),
    (sweep_cloud, sweep_cloud._log_clamp_cloud, "sweep_cloud"),
    (q3329_verify, q3329_verify._log_clamp, "q3329_verify"),
    (overnight_experiments, overnight_experiments._log_clamp, "overnight_experiments"),
    (run_3x_extended, run_3x_extended._log_clamp, "run_3x_extended"),
    (run_convergence_test, run_convergence_test._log_clamp, "run_convergence_test"),
]


def _exercise(module, wrapper, expected_name, tmp_path):
    """Redirect the wrapper's log_path to tmp_path, call it once, read back."""
    # sweep_cloud hardcodes /tmp/clamp_events.jsonl; all others read CLAMP_LOG_FILE.
    # Monkeypatch `log_clamp` at the module level to capture the log_path
    # that was actually requested, then call the real log_clamp with tmp_path.
    from _math_core import log_clamp as real_log_clamp
    captured = {}

    def wrapped_log_clamp(ctx, position, raw_value, *, script_name, log_path):
        captured["script_name"] = script_name
        captured["log_path"] = log_path
        # Redirect to tmp_path for the actual write so we don't touch
        # the real clamp_events.jsonl.
        real_log_clamp(ctx, position, raw_value,
                       script_name=script_name, log_path=tmp_path)

    with patch.object(module, "log_clamp", wrapped_log_clamp):
        wrapper("n100_beta30_seed99 active_block", 42, -1.23456e-5)

    with open(tmp_path) as f:
        line = f.readline().strip()
    record = json.loads(line)
    return captured, record


def _verify_record(record, captured, expected_name):
    failures = []
    expected_fields = {"ts", "level", "script", "cat", "msg"} - {"level", "cat", "msg"}
    expected_fields = {"ts", "script", "ctx", "position", "raw_value"}
    missing = expected_fields - set(record.keys())
    if missing:
        failures.append(f"missing fields: {missing}")
    if record.get("script") != expected_name:
        failures.append(
            f"script field: got {record.get('script')!r}, expected {expected_name!r}"
        )
    if captured.get("script_name") != expected_name:
        failures.append(
            f"wrapper passed script_name={captured.get('script_name')!r}, "
            f"expected {expected_name!r}"
        )
    if record.get("position") != 42:
        failures.append(f"position: got {record.get('position')!r}, expected 42")
    # raw_value round-trip with float precision
    if abs(record.get("raw_value", 0) - (-1.23456e-5)) > 1e-18:
        failures.append(
            f"raw_value: got {record.get('raw_value')!r}, expected -1.23456e-5"
        )
    return failures


def main():
    PIPELINE.info(
        "log_clamp wrapper test start",
        cat="validation", wrapper_count=len(WRAPPERS),
    )
    all_failures = []
    for module, wrapper, expected_name in WRAPPERS:
        with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".jsonl") as tf:
            tmp_path = tf.name
        try:
            captured, record = _exercise(module, wrapper, expected_name, tmp_path)
            fails = _verify_record(record, captured, expected_name)
            if fails:
                all_failures.append((expected_name, fails))
                print(f"  FAIL  {expected_name}: {fails}")
            else:
                print(f"  PASS  {expected_name}: "
                      f"log_path={captured['log_path']!r}")
        finally:
            os.unlink(tmp_path)

    print()
    if not all_failures:
        print(f"PASS — all {len(WRAPPERS)} clamp-log wrappers emit the "
              f"expected JSONL schema.")
        PIPELINE.info(
            "log_clamp wrapper test pass",
            cat="validation", wrapper_count=len(WRAPPERS), failures=0,
        )
        return 0

    print(f"FAIL — {len(all_failures)} wrapper(s) failed schema check.")
    PIPELINE.error(
        "log_clamp wrapper test fail",
        cat="validation",
        failures=len(all_failures),
        first_failure=all_failures[0][0],
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
