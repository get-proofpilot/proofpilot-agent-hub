#!/bin/bash
# Sync vault data from Obsidian to Agent Hub data directory.
# Run before deployment or on a cron to keep client data current.
#
# Usage: ./scripts/sync-vault-data.sh

VAULT_ROOT="$HOME/my-vault/client-work"
DATA_DIR="$(dirname "$0")/../backend/vault_data"

if [ ! -d "$VAULT_ROOT" ]; then
  echo "Error: Vault not found at $VAULT_ROOT"
  exit 1
fi

mkdir -p "$DATA_DIR/clients"

# Copy master client index
cp "$VAULT_ROOT/_clients-index.yaml" "$DATA_DIR/_clients-index.yaml"
echo "Copied _clients-index.yaml"

# Copy per-client files (strategy + work history)
for client_dir in "$VAULT_ROOT/clients"/*/; do
  client_name=$(basename "$client_dir")
  mkdir -p "$DATA_DIR/clients/$client_name"

  # Strategy files
  for file in recurring.yaml roadmap.yaml context.md; do
    if [ -f "$client_dir/$file" ]; then
      cp "$client_dir/$file" "$DATA_DIR/clients/$client_name/$file"
      echo "  $client_name/$file"
    fi
  done

  # Work history files (needed for audits and memory)
  if [ -f "$client_dir/log.md" ]; then
    cp "$client_dir/log.md" "$DATA_DIR/clients/$client_name/log.md"
    echo "  $client_name/log.md"
  fi

  if [ -f "$client_dir/tracker.yaml" ]; then
    cp "$client_dir/tracker.yaml" "$DATA_DIR/clients/$client_name/tracker.yaml"
    echo "  $client_name/tracker.yaml"
  fi

  # Monthly plans (for audit reference)
  if [ -d "$client_dir/monthly-plans" ]; then
    mkdir -p "$DATA_DIR/clients/$client_name/monthly-plans"
    cp "$client_dir"/monthly-plans/*.md "$DATA_DIR/clients/$client_name/monthly-plans/" 2>/dev/null
    plan_count=$(ls -1 "$DATA_DIR/clients/$client_name/monthly-plans/" 2>/dev/null | wc -l | tr -d ' ')
    [ "$plan_count" -gt 0 ] && echo "  $client_name/monthly-plans/ ($plan_count plans)"
  fi
done

echo ""
echo "Vault data synced to $DATA_DIR"
echo "Clients: $(ls -1 "$DATA_DIR/clients" | wc -l | tr -d ' ')"
