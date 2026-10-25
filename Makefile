# BKZ Dynamical Systems Benchmark — Makefile
#
# Single-command wrappers around the committed scripts. `make help` lists them.

.PHONY: help reproduce verify manifest manifest-patched lint-manifest xarch-compare vecprobe-membership figs figs-paper2 paper clean

help:  ## Show this menu
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_-]+:.*?## / {printf "  \033[36m%-28s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

reproduce:  ## Regenerate the 5 paper reference seeds + verify SHA-256 (fast: NUM_SEEDS=1)
	bash scripts/verify.sh

verify:  ## Run all CI gates locally (lint_logging, ruff, pytest, verify.sh, lint_seed_manifest)
	python3 scripts/lint_logging.py
	python3 -m ruff check scripts/ analysis/
	python3 -m pytest tests/ -v
	NUM_SEEDS=1 bash scripts/verify.sh
	python3 scripts/lint_seed_manifest.py

manifest:  ## Rebuild results/seed_manifest.json from the on-disk tree (byte-stable)
	python3 scripts/build_seed_manifest.py --deterministic

manifest-patched:  ## Rebuild results/patched_seed_manifest.json (Kahan engine, byte-stable)
	python3 scripts/build_patched_manifest.py

xarch-compare:  ## Cross-arch verdict: science-field compare ntru_xarch vs canonical ntru
	python3 scripts/compare_seed_trees.py

vecprobe-membership:  ## Rotation-span membership of stored short vectors (ntru_g6k_vecprobe tree)
	python3 scripts/vecprobe_membership.py

lint-manifest:  ## Fast orphan/ghost lint over seed_manifest.json
	python3 scripts/lint_seed_manifest.py

lint-manifest-sha:  ## Full --sha-check lint (recomputes SHA-256 of every seed; slow)
	python3 scripts/lint_seed_manifest.py --sha-check

figs:  ## Regenerate paper-1 figures into analysis/figures/
	python3 analysis/paper_figures.py

figs-paper2:  ## Regenerate paper-2 figures into paper2/latex/figs/
	python3 analysis/paper2_figures.py

paper2-claims:  ## Rebuild results/paper_claims/paper2_claims.json (claim provenance ledger)
	python3 scripts/build_paper2_claims.py

paper:  ## Rebuild the LaTeX PDF in paper1/latex/
	$(MAKE) -C paper1/latex

# ---------------------------------------------------------------------------
# Image rebuild targets. One target per image tag named in config/sweep.toml,
# the worklists or the scripts; tag -> Dockerfile + build args is documented in
# docs/images.md. These BUILD only (never `docker run`), and no other target
# depends on them. Each rebuilds the recipe as committed at HEAD; docs/images.md
# lists the commit each existing tag was built from where that differs.
# BUILD_JOBS only caps make -j (it does not change the binary); 4 leaves cores
# for a live sweep. Override: make image-g6k-ref BUILD_JOBS=
DOCKER ?= docker
BUILD_JOBS ?= 4
HOST_UID ?= $(shell id -u)
HOST_GID ?= $(shell id -g)
IMG_COMMON = --build-arg HOST_UID=$(HOST_UID) --build-arg HOST_GID=$(HOST_GID)
IMG_JOBS = --build-arg BUILD_JOBS=$(BUILD_JOBS)

.PHONY: images image-digests image-benchmark-ci image-g6k-ref image-g6k-ci image-g6k-dim256 image-g6k-dim384 image-g6k-dim384-inc63 image-g6k-dim384-reject image-fplll54

images:  ## List the image-* rebuild targets (builds nothing)
	@grep -E '^image-[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

image-digests:  ## Print image ID + RepoDigests for every tag in use (read-only)
	@for t in sdbkz-benchmark:ci sdbkz-g6k:ref sdbkz-g6k:ci sdbkz-g6k:dim256 \
	          sdbkz-g6k:dim384 sdbkz-g6k:dim384-inc63 sdbkz-g6k:dim384-reject \
	          sdbkz-fplll54; do \
	    out=$$($(DOCKER) image inspect --format '{{.Id}} {{.RepoDigests}} {{.Created}}' "$$t" 2>&1) || out="ABSENT ($$(printf '%s' "$$out" | tr -s '\n' ' '))"; \
	    printf '%s %s\n' "$$t" "$$out"; \
	done

image-benchmark-ci:  ## Build sdbkz-benchmark:ci (Dockerfile, fpylll 0.6.4 wheel)
	$(DOCKER) build -f Dockerfile $(IMG_COMMON) -t sdbkz-benchmark:ci .

image-g6k-ref:  ## Build sdbkz-g6k:ref (Dockerfile.g6k defaults: dim 128, gauss_sieve patch)
	$(DOCKER) build -f Dockerfile.g6k $(IMG_COMMON) $(IMG_JOBS) -t sdbkz-g6k:ref .

image-g6k-ci:  ## Build sdbkz-g6k:ci locally (same recipe CI builds)
	$(DOCKER) build -f Dockerfile.g6k $(IMG_COMMON) $(IMG_JOBS) -t sdbkz-g6k:ci .

image-g6k-dim256:  ## Build sdbkz-g6k:dim256 (G6K_MAX_SIEVING_DIM=256)
	$(DOCKER) build -f Dockerfile.g6k $(IMG_COMMON) $(IMG_JOBS) \
	    --build-arg G6K_MAX_SIEVING_DIM=256 -t sdbkz-g6k:dim256 .

image-g6k-dim384:  ## Build sdbkz-g6k:dim384 (dim 384, gauss_sieve patch NOT applied)
	$(DOCKER) build -f Dockerfile.g6k $(IMG_COMMON) $(IMG_JOBS) \
	    --build-arg G6K_MAX_SIEVING_DIM=384 --build-arg APPLY_INC63=0 \
	    -t sdbkz-g6k:dim384 .

image-g6k-dim384-inc63:  ## Build sdbkz-g6k:dim384-inc63 (dim 384, gauss_sieve patch applied)
	$(DOCKER) build -f Dockerfile.g6k $(IMG_COMMON) $(IMG_JOBS) \
	    --build-arg G6K_MAX_SIEVING_DIM=384 --build-arg APPLY_INC63=1 \
	    -t sdbkz-g6k:dim384-inc63 .

image-g6k-dim384-reject:  ## Build sdbkz-g6k:dim384-reject (dim 384, gauss_sieve patch + reject-on-overflow guard)
	$(DOCKER) build -f Dockerfile.g6k $(IMG_COMMON) $(IMG_JOBS) \
	    --build-arg G6K_MAX_SIEVING_DIM=384 --build-arg APPLY_INC63=1 \
	    --build-arg REJECT_OVERFLOW=1 -t sdbkz-g6k:dim384-reject .

image-fplll54:  ## Build sdbkz-fplll54 (fplll 5.4.5 + fpylll 0.6.0 sensitivity image)
	$(DOCKER) build -f Dockerfile.fplll54 $(IMG_COMMON) -t sdbkz-fplll54 .

clean:  ## Remove build artifacts (preserves seed data and logs)
	rm -f .tags
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache

# Notes:
# - No target ever deletes seed JSONs, logs, manifest, or anything under results/.
# - `clean` removes only build-layer caches (pycache, ctags index, pytest cache).
# - `reproduce` is the fastest "is this build correct?" check (~3 min on 22 workers).
# - `verify` runs the full CI gate chain; ~5 min end-to-end on a warm image.
