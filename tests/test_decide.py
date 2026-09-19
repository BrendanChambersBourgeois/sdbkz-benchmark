"""decide.py: the dismiss contract, the answer round trip, the rendered view.

Ported with decide.py from the HESTA vault copy (2026-09-19). The vault's
fixture built a temp vault and a temp day note and asserted both; this store
has neither, so those assertions are gone and DECISIONS.md beside the ledger
is the only rendered view. Ids start at Q01 here (the vault copy's empty-store
default was next_id 20, a migration constant for its own Q01..Q19).
"""
import datetime
import json
import os
import sys
import importlib

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("DECIDE_HOME", str(home))
    monkeypatch.setenv("DECIDE_OUT", str(tmp_path / "out"))
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    sys.modules.pop("decide", None)
    mod = importlib.import_module("decide")
    mod.args_require_fields = False   # the three fields are exercised in their own test
    return mod, home


def add(mod, q="Requeue the drained line?", topic="worklist", opts=("Requeue", "Hold"), kind="ruling"):
    data = mod.load_open()
    row = mod.new_question(data, {"q": q, "topic": topic, "opts": list(opts), "kind": kind, "ctx": "evidenced"})
    mod.save_open(data)
    return row["id"]


def test_store_is_isolated_from_the_vault_copy(env):
    """The ported module must never reach into the HESTA store or the vault."""
    mod, home = env
    assert mod.HOME == str(home)
    assert "obsidian" not in mod.OPEN and "obsidian" not in mod.LEDGER
    assert not hasattr(mod, "daynote_entry"), "the day-note writer must not survive the port"
    add(mod)
    assert os.path.exists(mod.OPEN)
    assert os.path.dirname(os.path.abspath(mod.OPEN)) == str(home)


def test_add_ids_start_at_one_and_duplicate_refused(env):
    mod = env[0]
    a = add(mod)
    assert a == "Q01"
    with pytest.raises(SystemExit):
        add(mod)  # same question text, still open
    assert add(mod, q="Second?") == "Q02"


def test_answer_round_trip_writes_ledger_and_note(env):
    mod, home = env
    qid = add(mod)
    data = mod.load_open()
    assert mod.apply_pending(data, {qid: {"choice": "Requeue", "note": "go"}}) == 1
    mod.save_open(data)
    mod.finish(mod.load_open(), "test")
    rows = mod.ledger_rows()
    assert len(rows) == 1 and rows[0]["outcome"] == "answered" and rows[0]["answer"] == "Requeue"
    assert rows[0]["q"] and rows[0]["ctx"] and rows[0]["opts"], "ledger row must read alone"
    note = (home / "DECISIONS.md").read_text()
    assert "| Q01 | worklist | ruling | Requeue the drained line? | evidenced | **Requeue** | go |" in note
    assert mod.state(mod.find(mod.load_open(), qid)) == "answered"
    assert mod.askable(mod.load_open()) == []


def test_dismiss_holds_until_context_changes(env):
    mod = env[0]
    qid = add(mod)
    data = mod.load_open()
    mod.apply_pending(data, {qid: {"choice": "__dismiss", "note": "not this quarter"}})
    mod.save_open(data)
    mod.finish(mod.load_open(), "test")
    data = mod.load_open()
    assert mod.state(mod.find(data, qid)) == "dismissed"
    assert mod.askable(data) == []
    # same context: a rebuild still skips it
    html, n = mod.build_html(data)
    assert n == 0
    # context changes: asked once more, flagged
    q = mod.find(data, qid)
    q["ctx"] = "new evidence 20-09"
    mod.save_open(data)
    data = mod.load_open()
    assert mod.state(mod.find(data, qid)) == "resurfaced"
    html, n = mod.build_html(data)
    assert n == 1 and '"resurfaced"' in html


def test_later_is_asked_again_and_other_keeps_text(env):
    mod = env[0]
    a = add(mod)
    b = add(mod, q="Which image?", opts=("kahan-v3", "reorder-control"))
    data = mod.load_open()
    mod.apply_pending(data, {a: {"choice": "__later"}, b: {"choice": "__other", "other": "dim384-inc63"}})
    mod.save_open(data)
    mod.finish(mod.load_open(), "test")
    data = mod.load_open()
    assert mod.state(mod.find(data, a)) == "later"
    assert [q["id"] for q in mod.askable(data)] == [a]
    assert mod.find(data, b)["answer"]["choice"] == "dim384-inc63"


def test_markdown_import_parses_page_export(env):
    mod = env[0]
    a = add(mod)
    b = add(mod, q="Which image?", opts=("kahan-v3", "reorder-control"))
    md = (f"## Decisions (2026-09-19 09:00)\n\n"
          f"- **{a} worklist** Requeue the drained line? → **Hold** *(after the drain)*\n"
          f"- **{b} worklist** Which image? → **Dismissed**\n")
    ans = mod.parse_answers(md)
    assert ans[a] == {"choice": "Hold", "note": "after the drain"}
    assert ans[b] == {"choice": "__dismiss", "note": ""}
    js = json.dumps({"answers": {a: {"choice": "Requeue", "note": ""}}})
    assert mod.parse_answers(js)[a]["choice"] == "Requeue"


def test_reopen_clears_and_logs(env):
    mod = env[0]
    qid = add(mod)
    data = mod.load_open()
    mod.apply_pending(data, {qid: {"choice": "__dismiss"}})
    mod.save_open(data)
    mod.finish(mod.load_open(), "test")

    class A:
        id = qid
        reason = "he asked"
    mod.cmd_reopen(A)
    assert mod.state(mod.find(mod.load_open(), qid)) == "open"
    assert mod.ledger_rows()[-1]["outcome"] == "reopened"


def test_stale_answer_for_answered_question_is_ignored(env):
    mod = env[0]
    a = add(mod)
    b = add(mod, q="Second?", opts=("X", "Y"))
    data = mod.load_open()
    mod.apply_pending(data, {a: {"choice": "Requeue"}})
    mod.save_open(data)
    mod.finish(mod.load_open(), "test")
    data = mod.load_open()
    # the browser posts both again; only the live one may take a pending answer
    n = mod.apply_pending(data, {a: {"choice": "Hold"}, b: {"choice": "X"}})
    assert n == 1
    mod.save_open(data)
    mod.finish(mod.load_open(), "test")
    rows = [r for r in mod.ledger_rows() if r["id"] == a]
    assert len(rows) == 1 and rows[0]["answer"] == "Requeue"


def test_the_three_fields_are_required_and_travel_to_the_ledger(env):
    mod = env[0]
    mod.args_require_fields = True
    data = mod.load_open()
    with pytest.raises(SystemExit):
        mod.new_question(data, {"q": "Bare?", "opts": ["A", "B"]})
    q = mod.new_question(data, {"q": "Full?", "opts": ["A", "B"], "investigated": "ledger, worklist",
                                "tried": "read the runner journal", "why_you": "the priority is yours"})
    mod.save_open(data)
    data = mod.load_open()
    mod.apply_pending(data, {q["id"]: {"choice": "A"}})
    mod.save_open(data)
    mod.finish(mod.load_open(), "test")
    row = mod.ledger_rows()[-1]
    assert (row["investigated"], row["tried"], row["why_you"]) == (
        "ledger, worklist", "read the runner journal", "the priority is yours")
    html, n = mod.build_html(mod.load_open())
    assert n == 0


def test_atomic_write_refuses_a_clobber(env):
    """The mtime guard is the only thing standing between a concurrent edit
    and a silent overwrite; the vault copy got this from taskcli."""
    mod, home = env
    path = str(home / "note.md")
    mod.atomic_write(path, "first\n")
    stale = os.stat(path).st_mtime_ns
    mod.atomic_write(path, "second\n", stale)          # unchanged: allowed
    os.utime(path, ns=(stale + 10**6, stale + 10**6))  # someone else edits
    with pytest.raises(SystemExit):
        mod.atomic_write(path, "third\n", stale)
    assert open(path).read() == "second\n"
