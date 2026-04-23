"""StrategyPilot manifest."""
from agents._template.manifest import AgentManifest

manifest = AgentManifest(
    id="strategypilot",
    title="StrategyPilot",
    description="SEO strategy document — footprint + competitive + page taxonomy + ROI model.",
    version="1.0.0",
    route_prefix="/api/agents/strategy",
    icon="🎯",
    category="strategy",
    owner="matthew",
    tags=("strategy", "seo", "roadmap"),
)
