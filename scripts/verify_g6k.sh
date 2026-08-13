#!/usr/bin/env bash
set -euo pipefail
#
# G6K determinism verify — byte-identity (SHA-256) gate for the
# single-threaded G6K sieve path. Mirrors verify.sh, but the G6K contract
# is bit-identical output (Phase 0), so the gate is an exact SHA match,
# not a 1e-4 tolerance compare.
#
# Regenerates ONE reference probe (fixed n, beta, seed, threads=1) inside
# the pinned image and compares its basis + r-profile SHA-256 against the
# reference recorded in results/g6k_seed_manifest.json. Any drift exits 1.
#
# Determinism contract (non-negotiable, Phase 0 verdict 2026-06-04):
#   threads=1 + FPLLL.set_random_seed(S) before basis AND again before the
#   sieve (g6k samples via fplll's global RNG) + same machine /
#   -march=x86-64-v2 build + default sieve params. NOTE: SieverParams has no
#   "seed" key in this build — it is a no-op, not part of the contract.
#   threads>1 is rejected by g6k_probe.py itself (exit 3).
#
# Container reproducibility chain (ADR-004 + ADR-005):
#   FROM python:3.12.3-bookworm@sha256:25dee7f137aa44c4962d21346385737eb
#                                       81954b6f06f519fcc348b67f6483d3c
#   apt mirror: snapshot.debian.org/archive/debian/20240614T000000Z/
#   fplll @1987472 · fpylll @e25ade8 (0.6.4) · g6k @c71e084 · march x86-64-v2
#
# Exit codes:
#   0  SHA matches reference (PASS)
#   1  SHA drift vs reference (FAIL)
#   2  manifest missing / unreadable
#   4  reference not yet captured (manifest holds the PENDING sentinel) —
#      run the first canonical build (see ADR-005 "capturing the reference")

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$BASE/results/g6k_seed_manifest.json"

PENDING_SENTINEL="PENDING-FIRST-BUILD"

echo "=== G6K Determinism Verify (single-threaded SHA gate) ==="
echo ""

if [ ! -f "$MANIFEST" ]; then
    echo "  ERROR: g6k manifest not found at $MANIFEST" >&2
    exit 2
fi

# Pull canonical reference params + expected SHAs from the manifest
# (the manifest is the single source of truth for the g6k SHA set).
read -r REF_N REF_BETA REF_SEED REF_BASIS REF_RPROF < <(python3 -c "
import json, sys
m = json.load(open('$MANIFEST'))
r = m['reference']
print(r['n'], r['beta'], r['seed'], r['basis_sha256'], r['rprof_sha256'])
")

if [ "$REF_BASIS" = "$PENDING_SENTINEL" ] || [ "$REF_RPROF" = "$PENDING_SENTINEL" ]; then
    echo "  PENDING: reference SHA not yet captured (manifest holds the" >&2
    echo "           $PENDING_SENTINEL sentinel)." >&2
    echo "" >&2
    echo "  Capture it from a clean pinned build on a target machine:" >&2
    echo "    docker build -f Dockerfile.g6k -t sdbkz-g6k:ref ." >&2
    echo "    docker run --rm sdbkz-g6k:ref \\" >&2
    echo "      python3 scripts/g6k_probe.py --n $REF_N --beta $REF_BETA --seed $REF_SEED --json" >&2
    echo "    # then write basis_sha256 + rprof_sha256 into $MANIFEST" >&2
    echo "    # and run scripts/lint_g6k_manifest.py --sha-check to confirm." >&2
    exit 4
fi

echo "Regenerating reference probe: n=$REF_N beta=$REF_BETA seed=$REF_SEED threads=1 ..."
GOT_JSON="$(python3 "$SCRIPT_DIR/g6k_probe.py" --n "$REF_N" --beta "$REF_BETA" --seed "$REF_SEED" --json)"
GOT_BASIS="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['basis_sha256'])" "$GOT_JSON")"
GOT_RPROF="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['rprof_sha256'])" "$GOT_JSON")"

echo ""
echo "Checking against reference (exact SHA-256 match required) ..."
fail=0

if [ "$GOT_BASIS" = "$REF_BASIS" ]; then
    echo "  PASS  basis  sha256 ${GOT_BASIS:0:16}…"
else
    echo "  FAIL  basis  got ${GOT_BASIS:0:16}… ref ${REF_BASIS:0:16}…"
    fail=1
fi
if [ "$GOT_RPROF" = "$REF_RPROF" ]; then
    echo "  PASS  rprof  sha256 ${GOT_RPROF:0:16}…"
else
    echo "  FAIL  rprof  got ${GOT_RPROF:0:16}… ref ${REF_RPROF:0:16}…"
    fail=1
fi

echo ""
if [ "$fail" -gt 0 ]; then
    echo "G6K VERIFICATION FAILED (byte-identity drift)"
    exit 1
fi
echo "G6K VERIFICATION PASSED"
exit 0
