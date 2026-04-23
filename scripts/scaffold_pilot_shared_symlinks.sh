#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PILOTS_DIR="$REPO_ROOT/backend/agents"

pilots=(auditpilot autopilot gbppilot pilotcore projectpilot qapilot redditpilot reportpilot strategypilot websitepilot)

for pilot in "${pilots[@]}"; do
  pilot_dir="$PILOTS_DIR/$pilot"
  if [[ ! -d "$pilot_dir" ]]; then
    echo "skip: $pilot (not a directory)"
    continue
  fi
  for shared in AGENTS.md USER.md; do
    target="$pilot_dir/$shared"
    if [[ -L "$target" ]]; then
      echo "ok:   $pilot/$shared (already linked)"
    elif [[ -e "$target" ]]; then
      echo "SKIP: $pilot/$shared exists as a real file — leave it"
    else
      ln -s "../../../$shared" "$target"
      echo "link: $pilot/$shared"
    fi
  done
done
