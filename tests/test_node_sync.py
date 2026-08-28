"""_classify_no_report — INC-58 follow-up: 'cannot authenticate' vs 'host down'.

A healthy node with no open ControlMaster socket used to be reported
identically to a dead one (reachable=False, nothing else)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from node_sync import _classify_no_report  # noqa: E402


def test_auth_failures_flag_socket_not_death():
    for err in ("deck@host: Permission denied (publickey).",
                "Host key verification failed.",
                "Confirm user presence for key ED25519-SK",
                "sign_and_send_pubkey: signing failed: agent refused operation",
                "Too many authentication failures"):
        out = _classify_no_report(255, err)
        assert "AUTH-BLOCKED" in out and "ControlMaster" in out, err


def test_network_failures_are_host_down():
    for err in ("ssh: connect to host 192.168.1.229 port 22: Connection timed out",
                "ssh: connect to host 192.168.1.229 port 22: No route to host",
                "ssh: connect to host 192.168.1.229 port 22: Connection refused",
                "ssh: Could not resolve hostname deck: Name or service not known",
                "connect to host x port 22: Network is unreachable"):
        assert "host down" in _classify_no_report(255, err), err


def test_timeout_is_reported_as_timeout():
    assert "timed out" in _classify_no_report(None, "")


def test_unknown_keeps_evidence():
    out = _classify_no_report(255, "something novel happened")
    assert "unknown" in out and "something novel" in out and "rc=255" in out
