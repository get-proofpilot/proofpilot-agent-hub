"""Pilot Core manifest."""
from agents._template.manifest import AgentManifest

manifest = AgentManifest(
    id="pilotcore",
    title="Pilot Core",
    description="Central AI coworker — aggregates client context, generates briefings, runs escalation checks.",
    version="1.0.0",
    route_prefix="/api/pilot",
    icon="🧭",
    category="operations",
    owner="matthew",
    tags=("briefing", "escalation", "context"),
)
