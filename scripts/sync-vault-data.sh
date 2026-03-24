#!/bin/bash
# Sync vault data from Obsidian to Agent Hub data directory.
# Run before deployment or on a cron to keep client data current.
#
# Usage: ./scripts/sync-vault-data.sh

VAULT_ROOT="$HOME/my-vault/client-work"
DATA_DIR="$(dirname "$0")/../data/vault"

if [ ! -d "$VAULT_ROOT" ]; then
  echo "Error: Vault not found at $VAULT_ROOT"
  exit 1
fi

mkdir -p "$DATA_DIR/clients"

# Copy master client index
cp "$VAULT_ROOT/_clients-index.yaml" "$DATA_DIR/_clients-index.yaml"
echo "Copied _clients-index.yaml"

# Copy per-client recurring.yaml and roadmap.yaml
for client_dir in "$VAULT_ROOT/clients"/*/; do
  client_name=$(basename "$client_dir")
  mkdir -p "$DATA_DIR/clients/$client_name"

  if [ -f "$client_dir/recurring.yaml" ]; then
    cp "$client_dir/recurring.yaml" "$DATA_DIR/clients/$client_name/recurring.yaml"
    echo "  $client_name/recurring.yaml"
  fi

  if [ -f "$client_dir/roadmap.yaml" ]; then
    cp "$client_dir/roadmap.yaml" "$DATA_DIR/clients/$client_name/roadmap.yaml"
    echo "  $client_name/roadmap.yaml"
  fi

  if [ -f "$client_dir/context.md" ]; then
    cp "$client_dir/context.md" "$DATA_DIR/clients/$client_name/context.md"
    echo "  $client_name/context.md"
  fi
done

echo ""
echo "Vault data synced to $DATA_DIR"
echo "Clients: $(ls -1 "$DATA_DIR/clients" | wc -l | tr -d ' ')"
