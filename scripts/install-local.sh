#!/usr/bin/env bash
# Install ProofPilot Pilots + workflow skills into ~/.claude/ via symlinks.
#
# Usage:
#   ./scripts/install-local.sh             # install
#   ./scripts/install-local.sh --dry-run   # print what would happen, don't link
#
# Idempotent. Refuses to overwrite non-symlink targets.

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
AGENTS_SRC="$REPO_ROOT/backend/agents"
WORKFLOW_SKILLS_SRC="$REPO_ROOT/backend/workflows/skills"

CLAUDE_AGENTS="$HOME/.claude/agents"
CLAUDE_SKILLS="$HOME/.claude/skills"

if [[ "$DRY_RUN" == "false" ]]; then
  mkdir -p "$CLAUDE_AGENTS" "$CLAUDE_SKILLS"
fi

linked=0
skipped=0
errors=0

link_one() {
  local src="$1"
  local dst="$2"

  if [[ ! -e "$src" ]]; then
    echo "ERROR: source missing: $src"
    errors=$((errors + 1))
    return
  fi

  if [[ -L "$dst" ]]; then
    local current
    current="$(readlink "$dst")"
    if [[ "$current" == "$src" ]]; then
      echo "ok:   $(basename "$dst") (already linked)"
      skipped=$((skipped + 1))
      return
    else
      echo "relink: $(basename "$dst") (was -> $current)"
      if [[ "$DRY_RUN" == "false" ]]; then
        rm "$dst"
        ln -s "$src" "$dst"
      fi
      linked=$((linked + 1))
      return
    fi
  elif [[ -e "$dst" ]]; then
    echo "ERROR: $dst exists and is not a symlink - refusing to overwrite"
    errors=$((errors + 1))
    return
  fi

  echo "link: $(basename "$dst") -> $src"
  if [[ "$DRY_RUN" == "false" ]]; then
    ln -s "$src" "$dst"
  fi
  linked=$((linked + 1))
}

# --- Pilot agents + skills ---
pilots=(auditpilot autopilot gbppilot pilotcore projectpilot qapilot redditpilot reportpilot strategypilot websitepilot)
for pilot in "${pilots[@]}"; do
  link_one "$AGENTS_SRC/$pilot/agent.md" "$CLAUDE_AGENTS/proofpilot-$pilot.md"
  link_one "$AGENTS_SRC/$pilot/skill"    "$CLAUDE_SKILLS/proofpilot-$pilot"
done

# --- Workflow skills ---
if [[ -d "$WORKFLOW_SKILLS_SRC" ]]; then
  for skill_dir in "$WORKFLOW_SKILLS_SRC"/pp-*; do
    [[ -d "$skill_dir" ]] || continue
    name="$(basename "$skill_dir")"
    link_one "$skill_dir" "$CLAUDE_SKILLS/$name"
  done
fi

echo ""
echo "Summary: $linked linked | $skipped already-linked | $errors errors"
if [[ "$DRY_RUN" == "true" ]]; then
  echo "(dry-run - nothing was actually changed)"
fi
if [[ "$errors" -ne 0 ]]; then
  exit 1
fi
