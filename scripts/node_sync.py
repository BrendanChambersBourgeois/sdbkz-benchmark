#!/usr/bin/env python3
"""Read status from, and pull results off, a remote compute node.

Runs on the WORKSTATION. Two subcommands:

    status   one live sample plus the node's recent history
    pull     copy new seeds into the canonical tree and merge the node's log

Both are safe to run repeatedly. `pull` never overwrites an existing seed
(rsync --ignore-existing) and never duplicates log lines: the node's
pipeline.jsonl records are keyed by timestamp and only unseen ones are
appended, so re-running is a no-op rather than a corruption.

SSH multiplexing is reused when a control socket is already open, so a
sequence of calls costs one hardware-key touch rather than one per call.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log import get_logger  # noqa: E402

PIPELINE = get_logger("node_sync")

REPO = Path(__file__).resolve().parent.parent
DEFAULT_NODE = "deck@192.168.1.229"
DEFAULT_CTRL = "/tmp/claude-1000/cm/%C"
DEFAULT_TREE = "ntru_g6k"


def _ssh_base(ctrl: str) -> list[str]:
    return ["ssh", "-o", "ControlMaster=auto", "-o", f"ControlPath={ctrl}",
            "-o", "ControlPersist=60m"]


def cmd_status(args: argparse.Namespace) -> int:
    ssh = _ssh_base(args.control_path) + [args.node]
    live = subprocess.run(
        ssh + [f"cd ~/{args.remote_dir} && python3 scripts/node_status.py "
               f"--unit {args.unit} --container {args.container} "
               f"--seed-dir ~/{args.remote_dir}/results/seeds/{args.tree}/{args.cell} "
               f"--expect-seeds {args.expect_seeds} --disk-path ~ 2>/dev/null"],
        capture_output=True, text=True, timeout=120)
    print(live.stdout.strip() or "(node did not report — unreachable or unit gone)")

    hist = subprocess.run(
        ssh + [f"jq -c 'select(.cat==\"node_status\") | "
               f"[.ts, .ctx.unit_active, .ctx.container_cpu_pct, .ctx.seeds_present]' "
               f"~/{args.remote_dir}/logs/pipeline.jsonl 2>/dev/null | tail -{args.history}"],
        capture_output=True, text=True, timeout=120)
    if hist.stdout.strip():
        print(f"\nlast {args.history} samples (ts, unit, cpu%, seeds):")
        print(hist.stdout.rstrip())
    PIPELINE.info("node status read", cat="node_sync", node=args.node,
                  reachable=bool(live.stdout.strip()))
    return 0 if live.stdout.strip() else 1


def _merge_log(node_lines: list[str], canonical: Path, node_name: str) -> tuple[int, int]:
    """Append only records this node has not already contributed."""
    seen: set[str] = set()
    if canonical.exists():
        with canonical.open() as fh:
            for line in fh:
                if '"node_sync"' not in line and '"node_status"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("ctx", {}).get("node") == node_name:
                    seen.add(rec.get("ts", ""))

    fresh = []
    for line in node_lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("ts") not in seen:
            fresh.append(line.rstrip("\n"))

    if fresh:
        with canonical.open("a") as fh:
            fh.write("\n".join(fresh) + "\n")
    return len(fresh), len(node_lines)


def cmd_pull(args: argparse.Namespace) -> int:
    ssh = _ssh_base(args.control_path)
    rsh = " ".join(ssh)
    dest = REPO / "results" / "seeds" / args.tree
    dest.mkdir(parents=True, exist_ok=True)

    rs = ["rsync", "-a", "--ignore-existing", "--itemize-changes", "-e", rsh,
          f"{args.node}:~/{args.remote_dir}/results/seeds/{args.tree}/", f"{dest}/"]
    if args.dry_run:
        rs.insert(1, "--dry-run")
    out = subprocess.run(rs, capture_output=True, text=True, timeout=1800)
    copied = [ln for ln in out.stdout.splitlines() if ln.strip()]
    print(f"seeds: {len(copied)} new file(s){' (dry-run)' if args.dry_run else ''}")
    for ln in copied[:20]:
        print(f"  {ln}")
    if out.returncode != 0:
        print(out.stderr.strip(), file=sys.stderr)
        return 2

    node_log = subprocess.run(
        ssh + [args.node, f"cat ~/{args.remote_dir}/logs/pipeline.jsonl 2>/dev/null"],
        capture_output=True, text=True, timeout=300)
    lines = [ln for ln in node_log.stdout.splitlines() if ln.strip()]
    canonical = REPO / "logs" / "pipeline.jsonl"
    if args.dry_run:
        print(f"log: {len(lines)} node record(s) available (dry-run, not merged)")
        added = 0
    else:
        added, total = _merge_log(lines, canonical, args.node_name or "steamdeck")
        print(f"log: appended {added} of {total} node record(s)")

    PIPELINE.info("node pull", cat="node_sync", node=args.node,
                  seeds_new=len(copied), log_appended=added, dry_run=args.dry_run)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--node", default=DEFAULT_NODE)
    ap.add_argument("--node-name", default="steamdeck", help="nodename as recorded in ctx.node")
    ap.add_argument("--remote-dir", default="lattice")
    ap.add_argument("--tree", default=DEFAULT_TREE, help="seed tree under results/seeds/")
    ap.add_argument("--control-path", default=DEFAULT_CTRL)
    sub = ap.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("status", help="live sample + recent history")
    st.add_argument("--unit", default="ntru-wall-b50-n179.service")
    st.add_argument("--container", default="ntru-wall-b50")
    st.add_argument("--cell", default="q4591/p500_mt50/n179_beta50")
    st.add_argument("--expect-seeds", type=int, default=10)
    st.add_argument("--history", type=int, default=8)
    st.set_defaults(func=cmd_status)

    pl = sub.add_parser("pull", help="copy new seeds + merge node log")
    pl.add_argument("--dry-run", action="store_true")
    pl.set_defaults(func=cmd_pull)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
