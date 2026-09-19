#!/usr/bin/env python3
"""decide: the questions only the owner can answer, asked once, on a local page.

Ported 2026-09-19 from ~/Desktop/obsidian/scripts/decide/decide.py, forked at
sha256 4b31ee33 (its obsidian commit b549d68), template.html at sha256
0ea3233d. That copy is the HESTA vault's and stays the HESTA vault's: it
renders its view into the vault and stamps the day note. This one is the
benchmark's, renders beside its own ledger, and has no vault. The two share no
state, and must not be pointed at each other's store: the vault copy's commit
overwrites HESTA/_Decisions.md from whatever ledger DECIDE_HOME names.

Carry a fix from upstream by diffing against that fork point, not by
re-copying — everything below the imports has been reworked.

Two kinds of question belong here and nothing else: a *ruling* (a call the
work is blocked on) and a *todo* (a thing only he can do and the work is
blocked on it). Anything the session can settle from the evidence on disk it
settles itself and records with `resolve`; it does not ask.

Stores, all local, all under DECIDE_HOME (default /mnt/hgfs/Research/decide,
outside the repo because rulings are narrative and the public surface stays
minimal):

  open.json      the standing list: every question ever added, with its state
  ledger.jsonl   append-only record of every outcome (answered, dismissed,
                 later, reopened), one JSON object per line, self-contained:
                 the question text, context, options and the answer travel
                 together so a reader needs nothing else
  DECISIONS.md   rendered view, regenerated from the ledger by `render` (and
                 by `finish`). The ledger is truth; this is a view.
  out/decide.html  the page; `build` embeds the askable questions into
                 scripts/decide_template.html and writes it here.

Ids are unique within a store, not across: this store and the vault's both
count from their own next_id, so cite a question as `topic Qnn`, never `Qnn`
alone.

Dismiss semantics. A dismissed question is never asked again while its
context is unchanged: `ctx_hash` is stored with the dismissal, and `build`
skips the question until the hash differs. New evidence changes the context
(`decide.py add` refuses a duplicate but `decide.py update ID --ctx ...` is
the edit path), the hash moves, the question comes back once with a
"previously dismissed" banner. `reopen ID` is the manual path.

Flow. `add` questions during the session; `ask` builds the page, serves it on
127.0.0.1, opens the browser, autosaves every click into open.json as
`pending`, and the page's Finish button commits (ledger, DECISIONS.md) and
stops the server. Static fallback: `build`, open the file, Download answers,
`import <file>`.
"""
import argparse
import datetime
import hashlib
import http.server
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from log import get_logger  # noqa: E402

log = get_logger("decide")

# The store lives outside the repo: rulings are narrative and the public
# surface stays minimal (CLAUDE.md, owner 2026-09-03). Research/ already
# holds ops/ and sessions/, so the decisions store sits beside them.
DEFAULT_HOME = "/mnt/hgfs/Research/decide"
HOME = os.environ.get("DECIDE_HOME") or DEFAULT_HOME
OPEN = os.path.join(HOME, "open.json")
LEDGER = os.path.join(HOME, "ledger.jsonl")
PIDFILE = os.path.join(HOME, "ask.pid")
TEMPLATE = os.path.join(HERE, "decide_template.html")
OUT_DIR = os.environ.get("DECIDE_OUT") or os.path.join(HOME, "out")
KINDS = ("ruling", "todo")
SPECIAL = ("__later", "__dismiss", "__other")
NOTE_REL = "DECISIONS.md"


def atomic_write(path, text, mtime=None):
    """Write text atomically; tmp + flush + fsync + os.replace.

    `mtime` is the st_mtime_ns the caller last saw: a mismatch means someone
    else edited the file since it was read, and the write is refused rather
    than clobbering them. The seed writer in _seed_io.py is the same shape but
    serialises JSON at a byte-identical indent the SHA gate depends on, so it
    is not the helper for free text.
    """
    if mtime is not None and os.path.exists(path) and os.stat(path).st_mtime_ns != mtime:
        die(f"{path} changed underneath us; not overwriting")
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def now():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")


def die(msg, code=2):
    print(f"decide: {msg}", file=sys.stderr)
    sys.exit(code)


def ctx_hash(q):
    h = hashlib.sha256((q.get("q", "") + "\n" + q.get("ctx", "") + "\n"
                        + "\n".join(q.get("opts", []))).encode()).hexdigest()
    return h[:10]


# ---------- stores ----------

def load_open():
    if not os.path.exists(OPEN):
        return {"next_id": 1, "questions": []}
    with open(OPEN, encoding="utf-8") as f:
        return json.load(f)


def save_open(data):
    atomic_write(OPEN, json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def ledger_append(rows):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def ledger_rows():
    if not os.path.exists(LEDGER):
        return []
    with open(LEDGER, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def state(q):
    if q.get("answer"):
        return "answered"
    if q.get("dismissed"):
        return "dismissed" if q["dismissed"].get("ctx_hash") == ctx_hash(q) else "resurfaced"
    if q.get("pending"):
        return "pending"
    if q.get("later"):
        return "later"
    return "open"


def askable(data):
    """Open, later, pending and resurfaced questions, the set the page shows."""
    out = []
    for q in data["questions"]:
        s = state(q)
        if s in ("open", "later", "pending", "resurfaced"):
            out.append(q)
    return out


# ---------- add / update / reopen ----------

args_require_fields = True


def new_question(data, d):
    kind = d.get("kind", "ruling")
    if kind not in KINDS:
        die(f"kind must be one of {KINDS}, got {kind!r}")
    if not d.get("q", "").strip():
        die("a question needs q")
    opts = [o.strip() for o in d.get("opts", []) if o.strip()]
    if len(opts) < 2:
        die(f"{d.get('q')!r}: at least two options (Later, Dismiss and Other are added by the page)")
    for q in data["questions"]:
        if q["q"].strip().lower() == d["q"].strip().lower() and state(q) != "answered":
            die(f"already open as {q['id']}: {q['q']}")
    qid = f"Q{data['next_id']:02d}"
    data["next_id"] += 1
    q = {"id": qid, "topic": d.get("topic", "").strip() or "General", "kind": kind,
         "q": d["q"].strip(), "ctx": d.get("ctx", "").strip(), "opts": opts,
         "ref": d.get("ref", "").strip(), "asked": str(datetime.date.today()),
         # 19-09 (Brendan): every question says what was checked, what the
         # session tried on its own, and why the call is his and not the tool's
         "investigated": d.get("investigated", "").strip(),
         "tried": d.get("tried", "").strip(),
         "why_you": d.get("why_you", "").strip()}
    if args_require_fields and not (q["investigated"] and q["tried"] and q["why_you"]):
        die(f"{qid} {q['q'][:50]!r}: investigated, tried and why_you are required (19-09 rule)")
    q["ctx_hash"] = ctx_hash(q)
    data["questions"].append(q)
    return q


def cmd_add(args):
    data = load_open()
    items = []
    if args.json:
        src = sys.stdin.read() if args.json == "-" else open(args.json, encoding="utf-8").read()
        parsed = json.loads(src)
        items = parsed if isinstance(parsed, list) else parsed.get("questions", [])
    else:
        if not args.q or not args.opt:
            die("give --q and at least two --opt, or --json")
        items = [{"topic": args.topic, "kind": args.kind, "q": args.q, "ctx": args.ctx or "",
                  "opts": args.opt, "ref": args.ref or "",
                  "investigated": args.investigated or "", "tried": args.tried or "",
                  "why_you": args.why_you or ""}]
    added = [new_question(data, d) for d in items]
    save_open(data)
    for q in added:
        print(f"added {q['id']} [{q['kind']}] {q['topic']}: {q['q']}")
    return 0


def find(data, qid):
    for q in data["questions"]:
        if q["id"] == qid:
            return q
    die(f"no question {qid}")


def cmd_update(args):
    data = load_open()
    q = find(data, args.id)
    before = ctx_hash(q)
    if args.ctx is not None:
        q["ctx"] = args.ctx.strip()
    if args.opt:
        q["opts"] = [o.strip() for o in args.opt]
    if args.q is not None:
        q["q"] = args.q.strip()
    q["ctx_hash"] = ctx_hash(q)
    save_open(data)
    moved = "context changed, will be asked again" if before != q["ctx_hash"] and q.get("dismissed") else "updated"
    print(f"{q['id']}: {moved}")
    return 0


def cmd_resolve(args):
    """A session found the answer on disk after the question was asked. Recorded
    as answered with source `session:<evidence>` so his rulings and the
    session's findings stay distinguishable in the ledger (19-09 rule: never
    hand him a question that already has an answer)."""
    data = load_open()
    q = find(data, args.id)
    if q.get("answer"):
        die(f"{q['id']} is already answered")
    ts = now()
    q["answer"] = {"choice": args.answer, "note": args.note or "", "ts": ts, "by": "session"}
    q.pop("later", None)
    q.pop("pending", None)
    q.pop("dismissed", None)
    row = {"ts": ts, "id": q["id"], "topic": q["topic"], "kind": q["kind"], "q": q["q"], "ctx": q["ctx"],
           "opts": q["opts"], "ref": q.get("ref", ""), "asked": q.get("asked", ""), "ctx_hash": ctx_hash(q),
           "outcome": "answered", "answer": args.answer, "note": args.note or "", "source": f"session:{args.evidence}"}
    save_open(data)
    ledger_append([row])
    render_note()
    print(f"{q['id']} resolved by the session: {args.answer}")
    return 0


def cmd_reopen(args):
    data = load_open()
    q = find(data, args.id)
    row = {"ts": now(), "id": q["id"], "topic": q["topic"], "kind": q["kind"], "q": q["q"],
           "outcome": "reopened", "was": state(q), "reason": args.reason or ""}
    for k in ("answer", "dismissed", "later", "pending"):
        q.pop(k, None)
    q["asked"] = str(datetime.date.today())
    save_open(data)
    ledger_append([row])
    print(f"{q['id']} reopened")
    return 0


# ---------- listing ----------

def cmd_ls(args):
    data = load_open()
    rows = data["questions"] if args.all else askable(data)
    if not rows:
        print("nothing open" if not args.all else "no questions")
        return 0
    for q in rows:
        s = state(q)
        tail = ""
        if s == "answered":
            tail = f" -> {q['answer']['choice']}"
        elif s == "dismissed":
            tail = f" (dismissed {q['dismissed']['ts'][:10]})"
        elif s == "resurfaced":
            tail = f" (dismissed {q['dismissed']['ts'][:10]}, context changed)"
        elif s == "pending":
            tail = f" (pending: {q['pending'].get('choice')})"
        print(f"{q['id']}  {s:10} [{q['kind']:6}] {q['topic']}: {q['q']}{tail}")
    counts = {}
    for q in data["questions"]:
        counts[state(q)] = counts.get(state(q), 0) + 1
    print(", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "0 questions")
    return 0


# ---------- build ----------

def build_html(data, mode="static"):
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    qs = []
    for q in askable(data):
        d = {k: q.get(k, "") for k in ("id", "topic", "kind", "q", "ctx", "opts", "ref", "asked",
                                       "investigated", "tried", "why_you")}
        if state(q) == "resurfaced":
            d["resurfaced"] = q["dismissed"]["ts"][:10]
        if q.get("pending"):
            d["pending"] = q["pending"]
        qs.append(d)
    payload = {"title": f"Decisions, {datetime.date.today().strftime('%d-%m-%Y')}",
               "subtitle": "Only what is blocked on you. One pick per question; Later asks again next time, "
                           "Dismiss stops asking until the context changes.",
               "mode": mode, "questions": qs}
    marker_a, marker_b = '<script type="application/json" id="questions">', "</script>"
    i = tpl.index(marker_a) + len(marker_a)
    j = tpl.index(marker_b, i)
    return tpl[:i] + "\n" + json.dumps(payload, ensure_ascii=False, indent=1) + "\n" + tpl[j:], len(qs)


def cmd_build(args):
    data = load_open()
    html, n = build_html(data, "static")
    os.makedirs(OUT_DIR, exist_ok=True)
    out = args.out or os.path.join(OUT_DIR, "decide.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"built {out} ({n} question(s))")
    return 0


# ---------- answers in ----------

def apply_pending(data, answers, ts=None):
    """answers: {id: {choice, other, note}} from the page. Stored as pending."""
    ts = ts or now()
    n = 0
    live = {q["id"] for q in askable(data)}
    for q in data["questions"]:
        a = answers.get(q["id"])
        # Only a question the page was showing can take an answer: the browser
        # keeps answers per page title, and on 19-09 a second run under the same
        # title posted the first run's five answers back, which re-committed
        # them (five duplicate ledger rows, removed by hand).
        if not a or not a.get("choice") or q["id"] not in live:
            q.pop("pending", None)
            continue
        q["pending"] = {"choice": a["choice"], "other": a.get("other", "").strip(),
                        "note": a.get("note", "").strip(), "ts": ts}
        n += 1
    return n


def commit_pending(data):
    """pending -> answered / dismissed / later, with ledger rows. Returns rows."""
    rows = []
    ts = now()
    for q in data["questions"]:
        p = q.pop("pending", None)
        if not p:
            continue
        base = {"ts": ts, "id": q["id"], "topic": q["topic"], "kind": q["kind"], "q": q["q"],
                "ctx": q["ctx"], "opts": q["opts"], "ref": q.get("ref", ""),
                "asked": q.get("asked", ""), "ctx_hash": ctx_hash(q), "note": p.get("note", ""),
                "investigated": q.get("investigated", ""), "tried": q.get("tried", ""),
                "why_you": q.get("why_you", "")}
        if p["choice"] == "__dismiss":
            q["dismissed"] = {"ts": ts, "ctx_hash": ctx_hash(q), "note": p.get("note", "")}
            q.pop("later", None)
            rows.append({**base, "outcome": "dismissed"})
        elif p["choice"] == "__later":
            q["later"] = {"ts": ts, "note": p.get("note", "")}
            rows.append({**base, "outcome": "later"})
        else:
            choice = (p.get("other") or "Other (blank)") if p["choice"] == "__other" else p["choice"]
            q["answer"] = {"choice": choice, "note": p.get("note", ""), "ts": ts}
            q.pop("later", None)
            q.pop("dismissed", None)
            rows.append({**base, "outcome": "answered", "answer": choice})
    return rows


def render_note():
    """DECISIONS.md beside the ledger, from the ledger and the open list.

    Deterministic. The vault original also appended a stamped entry to that
    day's day note; there is no day note here, so the rendered view is the
    only view and `finish` reports just it.
    """
    path = os.path.join(HOME, NOTE_REL)
    created = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            m = re.search(r"^created: (.+)$", f.read(), re.M)
            created = m.group(1) if m else None
    created = created or datetime.datetime.now().strftime("%a %d-%m-%Y %I:%M %p")
    rows = ledger_rows()
    data = load_open()
    latest = {}
    for r in rows:
        latest[r["id"]] = r
    answered = [r for r in rows if r["outcome"] == "answered"]
    answered.sort(key=lambda r: r["ts"], reverse=True)
    dismissed = [q for q in data["questions"] if state(q) == "dismissed"]
    open_qs = askable(data)

    def cell(s):
        return str(s or "").replace("|", "\\|").replace("\n", " ")

    out = [f"# Decisions (every call made on the decisions page), created {created}", "",
           "> Rendered from `ledger.jsonl` by `scripts/decide.py render`; edit the ledger, not this file. "
           "One row per answer, newest first, the question and its context kept with the answer so a row reads alone. "
           "Dismissed questions stay dismissed until their context changes. "
           "Tool: `scripts/decide.py` in the lattice repo; this store is outside it.", "",
           f"## Answered ({len(answered)})", "",
           "| Date | Id | Topic | Kind | Question | Context | Answer | Note | Ref |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in answered:
        out.append(f"| {r['ts'][:10]} | {r['id']} | {cell(r['topic'])} | {r['kind']} | {cell(r['q'])} | "
                   f"{cell(r.get('ctx'))} | **{cell(r['answer'])}**{' (session, from disk)' if str(r.get('source', '')).startswith('session:') else ''} | {cell(r.get('note'))} | {cell(r.get('ref'))} |")
    out += ["", f"## Dismissed ({len(dismissed)})", "",
            "| Since | Id | Topic | Question | Note | Asked again when |", "| --- | --- | --- | --- | --- | --- |"]
    for q in dismissed:
        out.append(f"| {q['dismissed']['ts'][:10]} | {q['id']} | {cell(q['topic'])} | {cell(q['q'])} | "
                   f"{cell(q['dismissed'].get('note'))} | context changes (hash `{q['dismissed']['ctx_hash']}`) or `reopen` |")
    out += ["", f"## Open ({len(open_qs)})", "",
            "| Asked | Id | Topic | Kind | Question | State |", "| --- | --- | --- | --- | --- | --- |"]
    for q in open_qs:
        out.append(f"| {q.get('asked', '')} | {q['id']} | {cell(q['topic'])} | {q['kind']} | {cell(q['q'])} | {state(q)} |")
    out.append("")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write(path, "\n".join(out))
    return path


def finish(data, source):
    rows = commit_pending(data)
    save_open(data)
    if not rows:
        print("nothing pending")
        return 0
    for r in rows:
        r["source"] = source
    ledger_append(rows)
    note = render_note()
    n_a = sum(r["outcome"] == "answered" for r in rows)
    n_d = sum(r["outcome"] == "dismissed" for r in rows)
    n_l = sum(r["outcome"] == "later" for r in rows)
    log.info("decisions committed", cat="decision", answered=n_a, dismissed=n_d,
             later=n_l, rows=len(rows), source=source, home=HOME)
    print(f"committed: {n_a} answered, {n_d} dismissed, {n_l} later; ledger +{len(rows)}; "
          f"{note} rendered")
    return 0


def stop_server():
    """A running `ask` holds its own copy of open.json in memory and autosaves
    over it, so a CLI finish must stop it first. He says "done" in chat more
    often than he presses Finish (19-09, first live run)."""
    if not os.path.exists(PIDFILE):
        return False
    try:
        pid = int(open(PIDFILE).read().strip())
        os.kill(pid, signal.SIGINT)
    except (ValueError, ProcessLookupError, PermissionError):
        os.remove(PIDFILE)
        return False
    for _ in range(40):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    if os.path.exists(PIDFILE):
        os.remove(PIDFILE)
    return True


def cmd_finish(args):
    if stop_server():
        print("stopped the running ask server, its autosaved answers are on disk")
    return finish(load_open(), "cli")


MD_LINE = re.compile(r"^- \*\*(Q\d+)[^*]*\*\* .*? → \*\*(.+?)\*\*(?: \*\((.*)\)\*)?\s*$")


def parse_answers(text):
    """Either the page's JSON download ({id: {choice, other, note}}) or its markdown."""
    text = text.strip()
    if text.startswith("{"):
        d = json.loads(text)
        return d.get("answers", d)
    answers = {}
    for line in text.splitlines():
        m = MD_LINE.match(line.strip())
        if not m:
            continue
        qid, ans, note = m.groups()
        if ans == "Later":
            answers[qid] = {"choice": "__later", "note": note or ""}
        elif ans == "Dismissed":
            answers[qid] = {"choice": "__dismiss", "note": note or ""}
        else:
            answers[qid] = {"choice": ans, "note": note or ""}
    return answers


def cmd_import(args):
    src = args.file
    if not src:
        dl = os.path.expanduser("~/Downloads")
        cands = sorted((os.path.join(dl, f) for f in os.listdir(dl) if f.startswith("decide-answers")),
                       key=os.path.getmtime)
        if not cands:
            die("no file given and nothing named decide-answers* in ~/Downloads")
        src = cands[-1]
    text = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
    answers = parse_answers(text)
    data = load_open()
    n = apply_pending(data, answers)
    known = {q["id"] for q in data["questions"]}
    unknown = sorted(set(answers) - known)
    if unknown:
        print(f"ignored unknown ids: {', '.join(unknown)}")
    print(f"{n} answer(s) read from {src}")
    return finish(data, f"import:{os.path.basename(src)}")


# ---------- ask: serve locally, autosave, finish from the page ----------

class Handler(http.server.SimpleHTTPRequestHandler):
    data = None
    done = threading.Event()
    lock = threading.Lock()
    summary = None

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.path = "/decide.html"
        return super().do_GET()

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n).decode("utf-8") if n else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return self._json(400, {"error": "bad json"})
        with Handler.lock:
            if self.path == "/save":
                k = apply_pending(Handler.data, payload.get("answers", {}))
                save_open(Handler.data)
                return self._json(200, {"saved": k, "ts": now()})
            if self.path == "/finish":
                apply_pending(Handler.data, payload.get("answers", {}))
                save_open(Handler.data)
                rows = commit_pending(Handler.data)
                save_open(Handler.data)
                for r in rows:
                    r["source"] = "page"
                if rows:
                    ledger_append(rows)
                    render_note()
                    log.info("decisions committed", cat="decision", rows=len(rows),
                             source="page", home=HOME)
                summary = {"answered": sum(r["outcome"] == "answered" for r in rows),
                           "dismissed": sum(r["outcome"] == "dismissed" for r in rows),
                           "later": sum(r["outcome"] == "later" for r in rows)}
                Handler.summary = summary
                self._json(200, summary)
                Handler.done.set()
                return None
        return self._json(404, {"error": "no such route"})


def cmd_ask(args):
    data = load_open()
    html, n = build_html(data, "served")
    if n == 0:
        print("nothing to ask")
        return 0
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "decide.html"), "w", encoding="utf-8") as f:
        f.write(html)
    Handler.data = data
    Handler.done.clear()
    os.chdir(OUT_DIR)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{srv.server_address[1]}/decide.html"
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    # flush: stdout block-buffers when it is not a TTY, and this is meant to be
    # run in the background, where the URL is the whole point of the line. Without
    # it the address sits in the buffer until the server exits.
    print(f"{n} question(s) at {url}  (Finish on the page commits; Ctrl-C keeps autosaved answers as pending)",
          flush=True)
    if not args.no_open:
        try:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            print(f"could not open a browser ({e}); open the URL yourself")
    try:
        while not Handler.done.wait(0.5):
            pass
        s = Handler.summary or {}
        print("finished from the page: " + ", ".join(f"{v} {k}" for k, v in s.items()))
    except KeyboardInterrupt:
        pend = sum(1 for q in data["questions"] if q.get("pending"))
        print(f"\nstopped; {pend} pending answer(s) kept in open.json, run `decide.py finish` to commit")
    finally:
        srv.shutdown()
        if os.path.exists(PIDFILE):
            os.remove(PIDFILE)
    return 0


# ---------- ledger views ----------

def cmd_ledger(args):
    rows = ledger_rows()
    if args.since:
        rows = [r for r in rows if r["ts"][:10] >= args.since]
    if args.topic:
        rows = [r for r in rows if r.get("topic", "").lower() == args.topic.lower()]
    if args.id:
        rows = [r for r in rows if r["id"] == args.id]
    if not rows:
        print("no ledger rows")
        return 0
    if args.json:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False))
        return 0
    for r in rows:
        if r["outcome"] == "answered":
            note = f"  ({r['note']})" if r.get("note") else ""
            who = " [session]" if str(r.get("source", "")).startswith("session:") else ""
            print(f"{r['ts']} {r['id']} {r['topic']}: {r['q']} -> {r['answer']}{who}{note}")
        elif r["outcome"] == "reopened":
            print(f"{r['ts']} {r['id']} {r['topic']}: reopened (was {r.get('was')}) {r.get('reason', '')}")
        else:
            note = f"  ({r['note']})" if r.get("note") else ""
            print(f"{r['ts']} {r['id']} {r['topic']}: {r['q']} -> {r['outcome'].upper()}{note}")
    return 0


def cmd_render(args):
    print(f"rendered {render_note()}")
    return 0


# ---------- main ----------

def main(argv=None):
    ap = argparse.ArgumentParser(prog="decide", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="add a question (flags, or --json FILE|- with a list)")
    p.add_argument("--topic", default="General")
    p.add_argument("--kind", default="ruling", choices=KINDS)
    p.add_argument("--q")
    p.add_argument("--ctx")
    p.add_argument("--opt", action="append", help="one option per flag, recommended first")
    p.add_argument("--ref", help="wikilink to the record note")
    p.add_argument("--investigated", help="what was checked on disk before asking (19-09 rule)")
    p.add_argument("--tried", help="what the session tried on its own (19-09 rule)")
    p.add_argument("--why-you", dest="why_you", help="why the call is his and not the tool's (19-09 rule)")
    p.add_argument("--json")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("update", help="edit a question; a context change re-asks a dismissed one")
    p.add_argument("id")
    p.add_argument("--q")
    p.add_argument("--ctx")
    p.add_argument("--opt", action="append")
    p.set_defaults(fn=cmd_update)

    p = sub.add_parser("resolve", help="the session found the answer on disk; record it as the session's, not his")
    p.add_argument("id")
    p.add_argument("--answer", required=True)
    p.add_argument("--evidence", required=True, help="where it was found, a path or note name")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_resolve)

    p = sub.add_parser("reopen", help="clear an answer or dismissal and ask again")
    p.add_argument("id")
    p.add_argument("--reason")
    p.set_defaults(fn=cmd_reopen)

    p = sub.add_parser("ls", help="list askable questions (--all for every state)")
    p.add_argument("--all", action="store_true")
    p.set_defaults(fn=cmd_ls)

    p = sub.add_parser("build", help="write the static page to out/decide/decide.html")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("ask", help="serve the page on 127.0.0.1, open the browser, commit on Finish")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--no-open", action="store_true")
    p.set_defaults(fn=cmd_ask)

    p = sub.add_parser("finish", help="commit pending answers (after Ctrl-C on ask)")
    p.set_defaults(fn=cmd_finish)

    p = sub.add_parser("import", help="read a downloaded answers file (JSON or markdown), commit")
    p.add_argument("file", nargs="?", help="default: newest ~/Downloads/decide-answers*")
    p.set_defaults(fn=cmd_import)

    p = sub.add_parser("ledger", help="print the record (--json for one object per line)")
    p.add_argument("--since", help="YYYY-MM-DD")
    p.add_argument("--topic")
    p.add_argument("--id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_ledger)

    p = sub.add_parser("render", help="regenerate DECISIONS.md from the ledger")
    p.set_defaults(fn=cmd_render)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
