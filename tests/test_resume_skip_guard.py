"""run_campaign resume-skip validation: a corrupt seed JSON is quarantined
aside (bytes preserved) and regenerated instead of wedging the cell forever
(audit 2026-07-04 #3, major 1)."""
import importlib
import json
import os

rc = importlib.import_module("run_campaign")


def test_valid_json_skips(tmp_path):
    p = tmp_path / "seed0001.json"
    p.write_text(json.dumps({"status": "completed"}))
    assert rc._resume_skip_valid(str(p)) is True


def test_truncated_json_flagged(tmp_path):
    p = tmp_path / "seed0001.json"
    p.write_text('{"status": "compl')
    assert rc._resume_skip_valid(str(p)) is False


def test_quarantine_preserves_bytes_and_frees_path(tmp_path):
    p = tmp_path / "seed0001.json"
    p.write_text('{"broken')
    bad = rc._quarantine_corrupt(str(p))
    assert not p.exists()                      # path freed for regeneration
    assert open(bad).read() == '{"broken'      # bytes preserved, never deleted
    assert not bad.endswith(".json")           # out of every *.json glob


def test_quarantine_never_overwrites_previous(tmp_path):
    p = tmp_path / "seed0001.json"
    p.write_text("first")
    b1 = rc._quarantine_corrupt(str(p))
    p.write_text("second")
    b2 = rc._quarantine_corrupt(str(p))
    assert b1 != b2
    assert open(b1).read() == "first" and open(b2).read() == "second"
    assert os.path.exists(b1) and os.path.exists(b2)
