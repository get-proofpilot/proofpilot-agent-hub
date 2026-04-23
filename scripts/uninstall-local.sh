#!/usr/bin/env bash
# Remove ProofPilot agent/skill symlinks installed by install-local.sh.
# Only removes symlinks whose target resolves into this repo - safe.
#
# Usage:
#   ./scripts/uninstall-local.sh             # remove
#   ./scripts/uninstall-local.sh --dry-run   # print what would be removed

set -euo pipefail

DRY_RUN=false
case "${1:-}" in
  "") ;;
  --dry-run) DRY_RUN=true ;;
  -h|--help)
    echo "Usage: $0 [--dry-run]"
    exit 0
    ;;
  *)
    echo "Usage: $0 [--dry-run]" >&2
    exit 2
    ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_AGENTS="$HOME/.claude/agents"
CLAUDE_SKILLS="$HOME/.claude/skills"

removed=0
kept=0

# Resolve a symlink's target to an absolute path WITHOUT following further links.
# Handles both absolute and relative link targets.
resolve_target() {
  local link="$1"
  local target
  target="$(readlink "$link")"
  if [[ "$target" = /* ]]; then
    printf '%s' "$target"
  else
    local link_dir
    link_dir="$(cd "$(dirname "$link")" && pwd)"
    printf '%s/%s' "$link_dir" "$target"
  fi
}

remove_if_ours() {
  local path="$1"
  [[ -L "$path" ]] || return 0
  local target
  target="$(resolve_target "$path")"
  if [[ "$target" == "$REPO_ROOT"/* ]]; then
    if [[ "$DRY_RUN" == "false" ]]; then
      rm "$path"
    fi
    echo "removed: $path"
    removed=$((removed + 1))
  else
    echo "kept:    $path (target outside this repo: $target)"
    kept=$((kept + 1))
  fi
}

# Pilot agents (proofpilot-<pilot>.md)
shopt -s nullglob
for agent_link in "$CLAUDE_AGENTS"/proofpilot-*.md; do
  remove_if_ours "$agent_link"
done

# Pilot + workflow skills (proofpilot-* and pp-*)
for skill_link in "$CLAUDE_SKILLS"/proofpilot-* "$CLAUDE_SKILLS"/pp-*; do
  remove_if_ours "$skill_link"
done
shopt -u nullglob

echo ""
echo "Summary: $removed removed | $kept kept (not ours)"
if [[ "$DRY_RUN" == "true" ]]; then
  echo "(dry-run - nothing was actually changed)"
fi
