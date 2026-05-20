#!/usr/bin/env python3
"""Compare /tmp/confirm_v1_2/ staging files against archives for the
out-of-band parallel groups launched by /tmp/launch_extra.sh.

Same compare logic as confirm_v1_2.py: strip timestamp/bkz_time/
sdbkz_time, check JSON byte-equality.
"""
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from log import get_logger  # noqa: E402

PIPELINE = get_logger("confirm_extra_compare")

STRIP = {"timestamp", "bkz_time", "sdbkz_time"}

GROUPS = [
    ("n=110 β=40", "results/cloud/n110_beta40_seed{s}.json",
     "/tmp/confirm_v1_2/sp_n110_b40_s{s}.json"),
    ("n=130 β=40", "results/cloud/n130_beta40_seed{s}.json",
     "/tmp/confirm_v1_2/sp_n130_b40_s{s}.json"),
    ("q=3329 n=90 1000-bit", "results/q3329_n90_beta30/n90_beta30_q3329_seed{s}.json",
     "/tmp/confirm_v1_2/q3329_n90_b30_s{s}.json"),
    ("cliff 500-bit n=130 β=40",
     "results/cliff_500bit/n130_beta40_q97_seed{s}.json",
     "/tmp/confirm_v1_2/cliff_500_n130_b40_s{s}.json"),
]


def _strip(path):
    with open(path) as f:
        d = json.load(f)
    for k in STRIP:
        d.pop(k, None)
    return json.dumps(d, sort_keys=True).encode()


def main():
    PIPELINE.info("confirm extras start", cat="validation",
                  groups=len(GROUPS))
    total_ok = 0
    total_fail = 0
    fails = []
    for label, archive_tmpl, staging_tmpl in GROUPS:
        print(f"\n=== {label} ===")
        ok = 0
        for s in range(1, 6):
            arch = os.path.join(REPO, archive_tmpl.format(s=s))
            stage = staging_tmpl.format(s=s)
            if not os.path.exists(arch):
                print(f"  seed {s}: archive missing")
                continue
            if not os.path.exists(stage):
                print(f"  seed {s}: staging not produced (still running?)")
                total_fail += 1
                fails.append((label, s, "no staging"))
                continue
            if _strip(arch) == _strip(stage):
                print(f"  seed {s}: PASS")
                ok += 1
                total_ok += 1
            else:
                print(f"  seed {s}: BYTE-DIFF")
                total_fail += 1
                fails.append((label, s, "byte-diff"))
        print(f"  {label}: {ok}/5 PASS")
    print()
    print("=" * 70)
    print(f"EXTRAS COMPLETE: {total_ok} PASS / {total_fail} FAIL")
    if fails:
        for f in fails:
            print(f"  {f}")
    print("=" * 70)
    PIPELINE.info("confirm extras complete", cat="validation",
                  ok=total_ok, fail=total_fail)
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
