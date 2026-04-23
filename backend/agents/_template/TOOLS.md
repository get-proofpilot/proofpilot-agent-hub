# TOOLS — Template Pilot

> The external systems and shared helpers this Pilot depends on.
> Keep this current — it's the blast-radius map for any infra change.

## Model providers

| Provider | Model | Purpose | Env var |
|---|---|---|---|
| Anthropic | claude-opus-4-6 | (describe use) | `ANTHROPIC_API_KEY` |

## Data / scraping

| Service | Endpoints used | Purpose |
|---|---|---|

## Shared internal modules

| Module | Why we need it |
|---|---|
| `backend/utils/docx_generator.py` | Branded `.docx` output |
| `backend/utils/db.py` | Job persistence |

## Agent-specific storage

| Path | Contents | Lifetime |
|---|---|---|

## Config / feature flags

- Reference `config.example.yaml` if present.
