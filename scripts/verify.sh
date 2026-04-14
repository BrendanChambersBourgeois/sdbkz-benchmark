#!/usr/bin/env bash
set -euo pipefail
#
# Verification sweep: runs N seeds at (n=50, beta=20) and compares
# against known-good reference values from the full experiment.
#
# Usage:
#   bash verify.sh              # run verification (default: 5 seeds)
#   bash verify.sh --check-only # skip computation, just check existing files
#   NUM_SEEDS=1 bash verify.sh  # fast mode (1 seed) — used by CI to save
#                                 runner minutes; still detects any build,
#                                 import, or numerical regression.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$(cd "$SCRIPT_DIR/.." && pwd)"
RAW_DIR="$BASE/results/raw"

NUM_SEEDS="${NUM_SEEDS:-5}"

# Reference values (n=50, beta=20, seeds 1-5). Only the first NUM_SEEDS
# lines are consumed at runtime, so NUM_SEEDS=1 runs only seed 1.
# Format: seed bkz_final_dln sdbkz_final_dln advantage
read -r -d '' REFERENCE <<'EOF' || true
1 4.022375 3.811012 0.211363
2 4.021647 3.846590 0.175056
3 4.024954 3.742366 0.282588
4 4.041260 3.718547 0.322714
5 3.941869 3.629196 0.312673
EOF

TOLERANCE=0.0001

echo "=== BKZ Dynamical Systems Benchmark — Verification ==="
echo ""

# Check numpy version (results depend on exact RNG output)
NUMPY_VER=$(python3 -c "import numpy; print(numpy.__version__)" 2>/dev/null || echo "NOT FOUND")
if [ "$NUMPY_VER" != "2.4.4" ]; then
    echo "WARNING: numpy version is $NUMPY_VER (expected 2.4.4)"
    echo "  Results may not match reference values due to RNG differences."
    echo ""
fi

# Run the first NUM_SEEDS verification seeds (unless --check-only)
if [[ "${1:-}" != "--check-only" ]]; then
    echo "Running verification seeds: n=50 beta=20 seeds 1-${NUM_SEEDS} ..."
    mkdir -p "$RAW_DIR"
    NUM_SEEDS="$NUM_SEEDS" python3 -c "
import sys, os
sys.path.insert(0, '$SCRIPT_DIR')
from sweep_parallel import run_single, RAW_DIR, result_path
import json, os

num_seeds = int(os.environ.get('NUM_SEEDS', '5'))
for seed in range(1, num_seeds + 1):
    out = result_path(50, 20, seed)
    if os.path.exists(out):
        print(f'  seed {seed}: already exists, skipping')
        continue
    print(f'  seed {seed}: running ...', end=' ', flush=True)
    result = run_single(50, 20, seed)
    with open(out, 'w') as f:
        json.dump(result, f, indent=2)
    print(f'done (advantage={result[\"advantage\"]:.6f})')
"
    echo ""
fi

# Check results against reference
echo "Checking first $NUM_SEEDS result(s) against reference values (tolerance=$TOLERANCE) ..."
echo ""

pass=0
fail=0
checked=0

while IFS=' ' read -r seed ref_bkz ref_sd ref_adv; do
    [ -z "$seed" ] && continue
    # Stop after NUM_SEEDS references checked
    if [ "$checked" -ge "$NUM_SEEDS" ]; then
        break
    fi
    checked=$((checked + 1))
    file="$RAW_DIR/n50_beta20_seed${seed}.json"

    if [ ! -f "$file" ]; then
        echo "  FAIL  seed $seed: result file missing"
        fail=$((fail + 1))
        continue
    fi

    got_bkz=$(python3 -c "import json; print(f'{json.load(open(\"$file\"))[\"bkz_final_dln\"]:.6f}')")
    got_sd=$(python3 -c "import json; print(f'{json.load(open(\"$file\"))[\"sdbkz_final_dln\"]:.6f}')")
    got_adv=$(python3 -c "import json; print(f'{json.load(open(\"$file\"))[\"advantage\"]:.6f}')")

    ok=$(python3 -c "
ref = ($ref_bkz, $ref_sd, $ref_adv)
got = ($got_bkz, $got_sd, $got_adv)
print('PASS' if all(abs(r-g) < $TOLERANCE for r,g in zip(ref,got)) else 'FAIL')
")

    if [ "$ok" = "PASS" ]; then
        echo "  PASS  seed $seed: advantage=$got_adv (ref=$ref_adv)"
        pass=$((pass + 1))
    else
        echo "  FAIL  seed $seed: bkz=$got_bkz(ref=$ref_bkz) sd=$got_sd(ref=$ref_sd) adv=$got_adv(ref=$ref_adv)"
        fail=$((fail + 1))
    fi
done <<< "$REFERENCE"

echo ""
echo "Results: $pass passed, $fail failed out of $NUM_SEEDS"

if [ "$fail" -gt 0 ]; then
    echo "VERIFICATION FAILED"
    exit 1
else
    echo "VERIFICATION PASSED"
    exit 0
fi
