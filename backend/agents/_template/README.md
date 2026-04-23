# Template Pilot

Copy this folder to scaffold a new agent. Replace every string
containing `template` / `_template`.

## Shape

```
<agent_id>/
├── __init__.py         # exports router + manifest
├── manifest.py         # metadata (id, title, route_prefix, version)
├── router.py           # APIRouter — auto-mounted at manifest.route_prefix
├── engine.py           # core logic
├── schemas.py          # Pydantic request/response models
├── prompts/            # .md prompt files (not Python strings)
│   └── system.md
├── examples/           # calibration samples (good / bad / edge) — not runtime-loaded
│   └── README.md
├── config.example.yaml # optional — only if the agent has runtime config
├── tests/              # pytest tests
├── CLAUDE.md           # scoped instructions for Claude Code sessions
├── SOUL.md             # identity, voice, boundaries
├── TOOLS.md            # integrations and shared modules this Pilot uses
└── README.md           # this file
```

## Adding a new agent

1. `cp -r backend/agents/_template backend/agents/<new_agent>`
2. Edit `manifest.py` — set `id`, `title`, `route_prefix`, etc.
3. Replace the prompt in `prompts/system.md`.
4. Write routes in `router.py` and logic in `engine.py`.
5. Restart the server — the auto-discovery loader picks it up.
