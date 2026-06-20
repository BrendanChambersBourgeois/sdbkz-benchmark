#!/usr/bin/env python3
"""Generate results/validation/verify_reference.json — the known-good reference
values verify.sh checks a fresh regeneration against.

Previously verify.sh carried these constants as inline bash literals; if they
were ever edited to match a regression, nothing would catch it (dev review).
Here they are derived from the committed, SHA-manifest-gated reference seeds
(results/seeds/main/q97/n050_beta20/), so the reference is anchored to data that
the manifest lints already guard against silent change -- and it is regenerable,
so an edited golden file no longer matches its own source.

Re-run intentionally (with review) only when the reference seeds themselves are
deliberately re-baselined.

Usage:
    python3 scripts/build_verify_reference.py
"""
from __future__ import annotations

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from log import get_logger  # noqa: E402
from sweep_parallel import result_path  # noqa: E402

PIPELINE = get_logger("build_verify_reference")
N, BETA, Q, SEEDS = 50, 20, 97, range(1, 6)
OUT = os.path.join(BASE, "results", "validation", "verify_reference.json")
_FIELDS = ("bkz_final_dln", "sdbkz_final_dln", "advantage")


def main() -> int:
    PIPELINE.info("build_verify_reference start", cat="verify",
                  n=N, beta=BETA, q=Q, out=os.path.relpath(OUT, BASE))
    seeds = []
    for s in SEEDS:
        path = result_path(N, BETA, s)
        with open(path) as f:
            doc = json.load(f)
        seeds.append({"seed": s, **{k: doc[k] for k in _FIELDS}})

    manifest = {
        "note": ("Known-good reference for verify.sh. Derived by "
                 "scripts/build_verify_reference.py from the committed, "
                 "SHA-manifest-gated seeds at results/seeds/main/q97/"
                 "n050_beta20/. Not hand-edited; regenerate to re-baseline."),
        "config": {"n": N, "beta": BETA, "q": Q},
        "source": "results/seeds/main/q97/n050_beta20/",
        "seeds": seeds,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, OUT)
    PIPELINE.info("build_verify_reference complete", cat="verify",
                  seeds=len(seeds), out=os.path.relpath(OUT, BASE))
    print(f"Wrote {os.path.relpath(OUT, BASE)}: {len(seeds)} reference seeds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
