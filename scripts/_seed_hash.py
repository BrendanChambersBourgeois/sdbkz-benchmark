"""Science-field hash for seed JSONs — single source of truth.

The deterministic hash over a seed result that EXCLUDES environment-dependent
fields (wall timings, timestamp, run status). Two runs of the same (campaign,
n, beta, seed, q, precision, max_tours) on different machines must produce the
same science_hash iff the numerical reduction is reproducible; the excluded
fields legitimately differ per-run/per-machine and would make a raw byte-diff
falsely fail.

Previously this logic lived inline only in validate_seeds.py (the --sha-check
spot-check). Centralised here so the cross-architecture compare tool
(compare_seed_trees.py) and validate_seeds share ONE definition and can never
drift. Path-only / no side effects on import, like _seed_paths.py.

The digest is byte-compatible with the pre-centralisation validate_seeds code:
    det = {k: v for k, v in sorted(d.items()) if k not in SCIENCE_EXCLUDE}
    sha256(json.dumps(det, sort_keys=True).encode()).hexdigest()
"""

from __future__ import annotations

import hashlib
import json
import os

# Environment-dependent fields excluded from the deterministic hash. Documented
# in results/hash_verification.txt; this set is the canonical definition.
SCIENCE_EXCLUDE = frozenset({"bkz_time", "sdbkz_time", "timestamp", "status"})


def science_hash(seed: dict | str | os.PathLike) -> str:
    """Return the SHA-256 hex digest over a seed's deterministic science fields.

    `seed` may be a parsed dict or a path to a seed JSON file. Excludes
    SCIENCE_EXCLUDE keys; the remaining fields are serialised as sorted-key
    JSON so the digest is order-independent and reproducible.
    """
    if isinstance(seed, dict):
        d = seed
    else:
        with open(seed) as fh:
            d = json.load(fh)
    det = {k: v for k, v in sorted(d.items()) if k not in SCIENCE_EXCLUDE}
    return hashlib.sha256(
        json.dumps(det, sort_keys=True).encode()
    ).hexdigest()
