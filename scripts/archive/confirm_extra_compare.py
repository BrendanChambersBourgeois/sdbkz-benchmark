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

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from _seed_paths import seed_path_for  # noqa: E402
from log import get_logger  # noqa: E402

PIPELINE = get_logger("confirm_extra_compare")

STRIP = {"timestamp", "bkz_time", "sdbkz_time"}


def _path(spec: dict, s: int) -> str:
    """Resolve one (group, seed-id) pair to its archive path.

    v2.0.0: routes through `_seed_paths.seed_path_for` so the canonical
    v1.3 tree under `results/seeds/<campaign>/` is the single source of
    truth. Legacy `results/cloud/...` + `results/q3329_n*_beta30/...`
    paths were deleted alongside the symlink drop.
    """
    return seed_path_for(**spec, seed=s)


# Per-group spec — kwargs forwarded to seed_path_for at lookup time.
# Cloud seeds carry the `_cloud` suffix; main-campaign main-sweep seeds
# do not. q3329 + cliff500 land in their own campaign trees.
GROUPS = [
    ("n=110 β=40",
     {"campaign": "main", "n": 110, "beta": 40, "cloud": True},
     "/tmp/confirm_v1_2/sp_n110_b40_s{s}.json"),
    ("n=130 β=40",
     {"campaign": "main", "n": 130, "beta": 40, "cloud": True},
     "/tmp/confirm_v1_2/sp_n130_b40_s{s}.json"),
    ("q=3329 n=90 1000-bit",
     {"campaign": "q3329", "n": 90, "beta": 30, "q": 3329,
      "precision": 1000, "max_tours": 70},
     "/tmp/confirm_v1_2/q3329_n90_b30_s{s}.json"),
    ("cliff 500-bit n=130 β=40",
     {"campaign": "cliff500", "n": 130, "beta": 40},
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
    for label, archive_spec, staging_tmpl in GROUPS:
        print(f"\n=== {label} ===")
        ok = 0
        for s in range(1, 6):
            arch = os.path.join(REPO, _path(archive_spec, s))
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
