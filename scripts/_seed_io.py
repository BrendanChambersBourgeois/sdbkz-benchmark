"""Shared seed-file I/O: atomic write, resume validation, corrupt quarantine.

Extracted verbatim from run_campaign.py, which was the only one of the four
runners that had them. sweep_parallel.py (the Docker CMD and the README
reproduction command, and the producer of the published paper-1
results/seeds/main/ tree), run_packed.py and run_3x_extended.py wrote seeds
non-atomically and resume-skipped on mere existence.

The serialisation is json.dump(obj, fh, indent=2) with no trailing newline --
byte-identical to what all four call sites already emitted, so SHA-256 seed
hashes and results/seed_manifest.json do not move.
"""

import json
import os


def write_seed_atomic(path: str, obj) -> None:
    """Write a seed JSON atomically and durably.

    tmp + flush + fsync + os.replace, so a crash mid-write never leaves a
    half-written seed JSON that breaks the resumable skip or the SHA gate.
    os.replace alone is atomic against SIGKILL, but the tmp file's CONTENTS
    need durability before the rename to survive power loss or a hard crash
    (INC-45 Phase 4b, overnight-run exposure; the Steam Machine node is a
    household games console that gets power-cycled mid-run).
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def resume_skip_valid(path: str) -> bool:
    """True if an existing seed JSON parses (safe to resume-skip).

    Existence alone is not proof a unit of work completed: a seed truncated by
    a power cut or an OOM kill exists, is unparseable, and under an
    existence-only skip wedges its cell forever.
    """
    try:
        with open(path) as fh:
            json.load(fh)
        return True
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False


def quarantine_corrupt(path: str) -> str:
    """Move a corrupt seed JSON aside (suffix .corrupt, numbered if needed) so
    the seed regenerates. The bytes are preserved, never deleted; the suffix
    keeps it out of every *.json glob (verdicts, manifest, extract)."""
    bad = path + ".corrupt"
    i = 1
    while os.path.exists(bad):
        i += 1
        bad = f"{path}.corrupt{i}"
    os.replace(path, bad)
    return bad
