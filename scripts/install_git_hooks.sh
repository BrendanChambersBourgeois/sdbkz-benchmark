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
#   - pre-commit: optional local guard, then scripts/check_new_top_level_dirs.py
#     (refuses commits that introduce un-allowlisted
#     new top-level directories in the public repo).
#   - commit-msg, pre-push: optional local guard only.
#
# Optional local guard: `git config --local hooks.localGuard /path/to/guard`
# names an executable called as `guard <hook-name> [hook args]`. Once it is
# set, every hook refuses to run without it (fail closed), so a reinstall
# never drops it silently.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOK_DIR="$(git rev-parse --git-path hooks)"

mkdir -p "$HOOK_DIR"

guard_prelude='G="$(git config --get hooks.localGuard || true)"
if [ -n "$G" ]; then
    [ -x "$G" ] || { echo "hooks.localGuard $G is set but not executable: refusing" >&2; exit 1; }
fi'

write_hook() {  # name, body after the guard call
  local name=$1 tail=$2
  cat > "$HOOK_DIR/$name" <<EOF
#!/usr/bin/env bash
# Auto-installed $name hook (regenerate via
# \`bash scripts/install_git_hooks.sh\`). Local-only; not tracked in git.
set -euo pipefail
$guard_prelude
$tail
EOF
  chmod +x "$HOOK_DIR/$name"
  echo "installed: $HOOK_DIR/$name"
}

write_hook pre-commit '[ -z "$G" ] || "$G" pre-commit
REPO_ROOT="$(git rev-parse --show-toplevel)"
exec python3 "$REPO_ROOT/scripts/check_new_top_level_dirs.py"'
write_hook commit-msg '[ -z "$G" ] || exec "$G" commit-msg "$1"'
write_hook pre-push '[ -z "$G" ] || exec "$G" pre-push'

guard="$(git config --get hooks.localGuard || true)"
echo "  local guard: ${guard:-none (set hooks.localGuard to add one)}"
