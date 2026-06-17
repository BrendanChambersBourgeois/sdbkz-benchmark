#!/usr/bin/env bash
# Phase C — n=113 β=40 cross-engine DSD-onset q-sweep, ONE self-proving command.
#
# The command IS the spec: cells, engines, workers, thread-pins, engine→tree
# mapping, and the extractor's --engine flag are all baked in here, committed.
# Nothing to hand-transcribe into a work order (see ops/vm_request_reproduce_
# first_20260613.md — this script is that ask applied to its own handoff).
#
# Usage:
#   scripts/run_phaseC.sh --dry-run     # print plan + run_packed dry-run, no build/run
#   scripts/run_phaseC.sh               # build-if-absent → verify (abort on SHA drift) → run → extract → tar
#   W_G6K=16 scripts/run_phaseC.sh      # override worker counts via env
#
# Idempotent + resumable: run_packed skips existing seeds, so re-running (or
# resuming a partial corpus checked out at a handoff SHA) only computes the gap.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# --- spec (single source) --------------------------------------------------
N=113; BETA=40; PREC=250; NSEEDS=40; MT=50
QS="167 197 239 281 317 359 401 439"
IMG_FPLLL="sdbkz-benchmark:ci"
IMG_G6K="sdbkz-g6k:dim256"            # n=113 → dim 2n=226 ≤ 256; matches existing ntru_g6k corpus
W_FPLLL="${W_FPLLL:-30}"
W_G6K="${W_G6K:-22}"
CELLS=""; for q in $QS; do CELLS="$CELLS ${N}:${q}:${PREC}:${NSEEDS}"; done

DRY=""; [ "${1:-}" = "--dry-run" ] && DRY="--dry-run"

run_engine() {  # $1 image  $2 workers  $3 seed-tag  $4 backend
  docker run --rm --user "$(id -u):$(id -g)" \
    -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 \
    -e MKL_NUM_THREADS=1 -e NUMEXPR_NUM_THREADS=1 \
    -v "$PWD":/work -w /work "$1" \
    python3 scripts/run_packed.py --workers "$2" --beta "$BETA" --mt "$MT" \
      --seed-tag "$3" --backend "$4" $DRY $CELLS
}

if [ -n "$DRY" ]; then
  echo ">>> Phase C plan: n=$N β=$BETA p=$PREC N=$NSEEDS, q∈{${QS// /,}}"
  echo ">>> g6k ($IMG_G6K, ${W_G6K}w) then fplll ($IMG_FPLLL, ${W_FPLLL}w), threads=1, skip-existing"
  echo "--- g6k dry-run ---";   run_engine "$IMG_G6K"  "$W_G6K"  ntru_g6k g6k
  echo "--- fplll dry-run ---"; run_engine "$IMG_FPLLL" "$W_FPLLL" ntru    fplll
  exit 0
fi

# --- step 0: prove the environment before generating a single seed ---------
echo ">>> [0/3] build images if absent + verify (ABORT on SHA drift)"
docker image inspect "$IMG_FPLLL" >/dev/null 2>&1 || docker build -f Dockerfile -t "$IMG_FPLLL" .
docker image inspect "$IMG_G6K"   >/dev/null 2>&1 || \
  docker build -f Dockerfile.g6k --build-arg G6K_MAX_SIEVING_DIM=256 -t "$IMG_G6K" .
docker run --rm -v "$PWD":/work -w /work "$IMG_G6K"   bash scripts/verify_g6k.sh   # g6k determinism gate
docker run --rm -v "$PWD":/work -w /work "$IMG_FPLLL" bash scripts/verify.sh       # 5 reference seeds, SHA-exact
echo ">>> environment verified."

# --- step 1: generate (g6k then fplll; sequential; resumable) --------------
echo ">>> [1/3] g6k half"  ; run_engine "$IMG_G6K"  "$W_G6K"  ntru_g6k g6k
echo ">>> [2/3] fplll half"; run_engine "$IMG_FPLLL" "$W_FPLLL" ntru    fplll

# --- step 2: extract onset (FLAG IS --engine, NOT --seed-tag) --------------
echo ">>> [3/3] extract onset + tar"
mkdir -p ops   # don't let tee/tar trip set -e on a fresh clone after a 30h run
for eng in fplll g6k; do
  docker run --rm -v "$PWD":/work -w /work "$IMG_FPLLL" \
    python3 scripts/extract_dsd_onset.py --n "$N" --beta "$BETA" --engine "$eng" --show-curve \
    | tee "ops/phaseC_n${N}_${eng}_onset.txt"
done

# --- step 3: tar both trees for shipback -----------------------------------
SHORT="$(git rev-parse --short HEAD)"
tar czf "ops/phaseC_n${N}_b${BETA}_${SHORT}.tar.gz" \
  results/seeds/ntru/q{167,197,239,281,317,359,401,439}/p${PREC}_mt${MT}/n${N}_beta${BETA} \
  results/seeds/ntru_g6k/q{167,197,239,281,317,359,401,439}/p${PREC}_mt${MT}/n${N}_beta${BETA} 2>/dev/null || true
echo ">>> Phase C complete. Onset → ops/phaseC_n${N}_*_onset.txt ; seeds → ops/phaseC_n${N}_b${BETA}_${SHORT}.tar.gz"
