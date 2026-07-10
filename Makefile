# BKZ Dynamical Systems Benchmark — Makefile
#
# Single-command wrappers around the existing scripts. Every target below
# is a thin shell over a committed script — see CONTRIBUTING.md for the
# underlying invocations.
#
# Invoke `make help` for the menu.

.PHONY: help reproduce verify bug-hunt manifest manifest-patched lint-manifest xarch-compare figs figs-paper2 paper clean

help:  ## Show this menu
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

reproduce:  ## Regenerate the 5 paper reference seeds + verify SHA-256 (fast: NUM_SEEDS=1)
	bash scripts/verify.sh

verify:  ## Run all CI gates locally (lint_logging, ruff, pytest, verify.sh, lint_seed_manifest)
	python3 scripts/lint_logging.py
	python3 -m ruff check scripts/ analysis/
	python3 -m pytest tests/ -v
	NUM_SEEDS=1 bash scripts/verify.sh
	python3 scripts/lint_seed_manifest.py

bug-hunt:  ## Static tag-driven bug hunt over scripts/ + analysis/ + tests/
	ctags -R --languages=python --python-kinds=-iv -f .tags \
	    scripts/ analysis/ tests/
	python3 scripts/find_bugs_via_tags.py

manifest:  ## Rebuild results/seed_manifest.json from the on-disk tree (byte-stable)
	python3 scripts/build_seed_manifest.py --deterministic

manifest-patched:  ## Rebuild results/patched_seed_manifest.json (Kahan engine, byte-stable)
	python3 scripts/build_patched_manifest.py

xarch-compare:  ## Cross-arch verdict: science-field compare ntru_xarch vs canonical ntru
	python3 scripts/compare_seed_trees.py

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

clean:  ## Remove build artifacts (preserves seed data and logs)
	rm -f .tags
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache

# Notes:
# - No target ever deletes seed JSONs, logs, manifest, or anything under results/.
# - `clean` removes only build-layer caches (pycache, ctags index, pytest cache).
# - `reproduce` is the fastest "is this build correct?" check (~3 min on 22 workers).
# - `verify` runs the full CI gate chain; ~5 min end-to-end on a warm image.
