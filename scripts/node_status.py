#!/usr/bin/env python3
"""Sample a remote compute node's campaign state into pipeline.jsonl.

Runs on the NODE (outside the container), not on the workstation: it reads
systemd --user, podman, and the on-disk seed tree, emits one `node_status`
record per invocation, and prints a one-line human summary.

Driven by a systemd --user timer so the node accumulates a timeline while
nobody is connected. Read it back with jq over logs/pipeline.jsonl:

    jq -c 'select(.cat=="node_status")' logs/pipeline.jsonl | tail -20

The node keeps its own pipeline.jsonl; append it to the canonical log, never
copy over it (logs are append-only).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log import get_logger  # noqa: E402

PIPELINE = get_logger("node_status")


def _run(cmd: list[str], timeout: int = 20) -> str:
    """Best-effort capture; a missing tool or dead unit is data, not an error."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def unit_state(unit: str) -> dict[str, str]:
    out = _run([
        "systemctl", "--user", "show", unit,
        "-p", "ActiveState", "-p", "SubState", "-p", "Result",
        "-p", "ActiveEnterTimestampMonotonic",
    ])
    kv = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return {
        "unit_active": kv.get("ActiveState", "unknown"),
        "unit_sub": kv.get("SubState", "unknown"),
        "unit_result": kv.get("Result", "unknown"),
    }


_UNITS = {"B": 1, "KB": 1e3, "KIB": 1024, "MB": 1e6, "MIB": 1024**2,
          "GB": 1e9, "GIB": 1024**3}


def _pct(v: object) -> float:
    """podman reports percentages as strings like "592.82%"."""
    try:
        return round(float(str(v).rstrip("%")), 1)
    except (TypeError, ValueError):
        return 0.0


def _mb(v: object) -> float:
    """Left side of a podman "462.7MB / 16.36GB" usage string, in MB."""
    text = str(v).split("/")[0].strip()
    num = "".join(c for c in text if c.isdigit() or c == ".")
    unit = text[len(num):].strip().upper()
    try:
        return round(float(num) * _UNITS.get(unit, 1) / 1e6, 1)
    except ValueError:
        return 0.0


def container_state(name: str) -> dict[str, object]:
    raw = _run(["podman", "stats", "--no-stream", "--format", "json", name], timeout=40)
    try:
        rows = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        rows = []
    if not rows:
        return {"container_up": False}
    row = rows[0]
    # Key spelling differs across podman versions: 5.x emits snake_case in JSON
    # while the Go-template path exposes .CPU / .MemUsage.
    return {
        "container_up": True,
        "container_cpu_pct": _pct(row.get("cpu_percent") or row.get("CPU")),
        "container_mem_mb": _mb(row.get("mem_usage") or row.get("MemUsage")),
        "container_pids": int(row.get("pids") or row.get("PIDS") or 0),
    }


def host_state(path: str) -> dict[str, float]:
    load1 = float(open("/proc/loadavg").read().split()[0])
    mem = {}
    for line in open("/proc/meminfo"):
        k, _, v = line.partition(":")
        mem[k] = int(v.split()[0])
    st = os.statvfs(path)
    return {
        "load1": load1,
        "mem_avail_mb": mem.get("MemAvailable", 0) // 1024,
        "disk_free_gb": round(st.f_bavail * st.f_frsize / 1e9, 1),
    }


def seed_progress(seed_dir: str | None, expect: int | None) -> dict[str, int]:
    if not seed_dir:
        return {}
    found = len(list(Path(seed_dir).glob("seed*.json"))) if Path(seed_dir).is_dir() else 0
    out = {"seeds_present": found}
    if expect:
        out["seeds_expected"] = expect
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--unit", required=True, help="systemd --user unit driving the campaign")
    ap.add_argument("--container", default=None, help="podman container name, if any")
    ap.add_argument("--seed-dir", default=None, help="cell directory to count seed*.json in")
    ap.add_argument("--expect-seeds", type=int, default=None, help="target seed count for that cell")
    ap.add_argument("--disk-path", default=str(Path.home()), help="path to report free space for")
    args = ap.parse_args()

    rec: dict[str, object] = {"node": os.uname().nodename, "unit": args.unit}
    rec.update(unit_state(args.unit))
    if args.container:
        rec.update(container_state(args.container))
    rec.update(host_state(args.disk_path))
    rec.update(seed_progress(args.seed_dir, args.expect_seeds))

    running = rec.get("unit_active") == "active"
    PIPELINE.info(
        f"node sample: {args.unit} {rec.get('unit_active')}/{rec.get('unit_sub')}",
        cat="node_status",
        **rec,
    )

    seeds = ""
    if "seeds_present" in rec:
        seeds = f" seeds={rec['seeds_present']}"
        if "seeds_expected" in rec:
            seeds += f"/{rec['seeds_expected']}"
    cpu = (f" cpu={rec['container_cpu_pct']}% mem={rec['container_mem_mb']}MB"
           f" pids={rec['container_pids']}") if rec.get("container_up") else ""
    print(
        f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {rec['node']} {args.unit} "
        f"{rec.get('unit_active')}/{rec.get('unit_sub')}"
        f"{cpu}{seeds} load={rec['load1']} mem_avail={rec['mem_avail_mb']}MB "
        f"disk_free={rec['disk_free_gb']}GB"
    )
    return 0 if running else 1


if __name__ == "__main__":
    raise SystemExit(main())
