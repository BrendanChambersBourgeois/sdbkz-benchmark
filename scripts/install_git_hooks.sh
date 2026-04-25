#!/usr/bin/env bash
# Install local git hooks for this repo.
#
# Hooks are local-only by git design (they live in .git/hooks/, which
# is never committed). This script regenerates them from the canonical
# templates kept in this repo so a fresh clone gets the same guard rails
# the original author runs with.
#
# Run once after cloning:
#   bash scripts/install_git_hooks.sh
#
# Currently installs:
#   - pre-commit: runs scripts/check_new_top_level_dirs.py
#     (INC-39 guard — refuses commits that introduce un-allowlisted
#     new top-level directories in the public repo).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOK_DIR="$REPO_ROOT/.git/hooks"

mkdir -p "$HOOK_DIR"

cat > "$HOOK_DIR/pre-commit" <<'EOF'
#!/usr/bin/env bash
# Auto-installed pre-commit hook (regenerate via
# `bash scripts/install_git_hooks.sh`). Local-only; not tracked in git.
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
exec python3 "$REPO_ROOT/scripts/check_new_top_level_dirs.py"
EOF

chmod +x "$HOOK_DIR/pre-commit"
echo "installed: $HOOK_DIR/pre-commit"
echo "  → runs scripts/check_new_top_level_dirs.py on every commit"
