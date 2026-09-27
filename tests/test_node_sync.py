"""_classify_no_report — INC-58 follow-up: 'cannot authenticate' vs 'host down'.

A healthy node with no open ControlMaster socket used to be reported
identically to a dead one (reachable=False, nothing else)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import json  # noqa: E402
import stat  # noqa: E402

from node_sync import _classify_no_report, _merge_log, _secure_ctrl_dir  # noqa: E402


def test_auth_failures_flag_socket_not_death():
    for err in ("deck@host: Permission denied (publickey).",
                "Host key verification failed.",
                "Confirm user presence for key ED25519-SK",
                "sign_and_send_pubkey: signing failed: agent refused operation",
                "Too many authentication failures"):
        out = _classify_no_report(255, err)
        assert "AUTH-BLOCKED" in out and "ControlMaster" in out, err


def test_network_failures_are_host_down():
    for err in ("ssh: connect to host deck port 22: Connection timed out",
                "ssh: connect to host deck port 22: No route to host",
                "ssh: connect to host deck port 22: Connection refused",
                "ssh: Could not resolve hostname deck: Name or service not known",
                "connect to host x port 22: Network is unreachable"):
        assert "host down" in _classify_no_report(255, err), err


def test_timeout_is_reported_as_timeout():
    assert "timed out" in _classify_no_report(None, "")


def test_unknown_keeps_evidence():
    out = _classify_no_report(255, "something novel happened")
    assert "unknown" in out and "something novel" in out and "rc=255" in out


# ---------- _merge_log: node lines are untrusted data ----------

def _rec(i):
    return json.dumps({"ts": f"2026-09-27T00:00:0{i}.000+00:00", "level": "INFO",
                       "script": "x", "cat": "t", "msg": f"m{i}"})


def test_merge_skips_non_object_lines_and_counts_them(tmp_path):
    canon = tmp_path / "pipeline.jsonl"
    canon.write_text(_rec(0) + "\n")
    before = canon.read_bytes()
    lines = [_rec(0), _rec(1), "not json", '["a list"]', "42", '{"trunc', _rec(2), ""]
    added, offered, invalid = _merge_log(lines, canon, "steamdeck")
    assert (added, offered, invalid) == (2, 8, 4)
    after = canon.read_bytes()
    assert after.startswith(before), "append-only: existing bytes untouched"
    rows = [json.loads(ln) for ln in after.decode().splitlines()]
    assert [r["msg"] for r in rows] == ["m0", "m1", "m2"]


def test_merge_is_idempotent_and_verbatim(tmp_path):
    canon = tmp_path / "pipeline.jsonl"
    lines = [_rec(1), _rec(2)]
    assert _merge_log(lines, canon, "steamdeck")[0] == 2
    assert _merge_log(lines, canon, "steamdeck")[0] == 0
    assert canon.read_text().splitlines() == lines


def test_merge_does_not_splice_onto_unterminated_last_line(tmp_path):
    canon = tmp_path / "pipeline.jsonl"
    canon.write_text(_rec(0))  # no trailing newline
    _merge_log([_rec(1)], canon, "steamdeck")
    assert canon.read_text().splitlines() == [_rec(0), _rec(1)]


# ---------- ControlMaster directory ----------

def test_ctrl_dir_created_private(tmp_path):
    ctrl = tmp_path / "cm" / "%C"
    assert _secure_ctrl_dir(str(ctrl)) is None
    assert stat.S_IMODE((tmp_path / "cm").stat().st_mode) == 0o700


def test_ctrl_dir_group_writable_is_tightened(tmp_path):
    d = tmp_path / "cm"
    d.mkdir()
    os.chmod(d, 0o775)
    assert _secure_ctrl_dir(str(d / "%C")) is None
    assert stat.S_IMODE(d.stat().st_mode) == 0o700


def test_ctrl_dir_symlink_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    (tmp_path / "cm").symlink_to(real)
    err = _secure_ctrl_dir(str(tmp_path / "cm" / "%C"))
    assert err and "refusing" in err
