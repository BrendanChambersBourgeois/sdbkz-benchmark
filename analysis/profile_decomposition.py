"""Write results/profile_decomposition.json: the head/mid/tail decomposition of
every main-campaign group (supplement to Paper 1 Table 5), via
analysis.tables.spatial_decomposition. Run: make decomposition."""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from log import get_logger  # noqa: E402

from analysis._data import load_all_seeds  # noqa: E402
from analysis.tables import spatial_decomposition  # noqa: E402

PIPELINE = get_logger("profile_decomposition")
OUT = os.path.join(REPO_ROOT, "results", "profile_decomposition.json")


def main():
    recs = spatial_decomposition(load_all_seeds(campaign="main", min_seeds=1))
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({f"n={r['n']}_beta={r['beta']}": r for r in recs}, fh, indent=2)
        fh.write("\n")
    PIPELINE.info("profile decomposition written", cat="analysis", groups=len(recs),
                  path=os.path.relpath(OUT, REPO_ROOT))


if __name__ == "__main__":
    main()
