"""QAPilot manifest."""
from agents._template.manifest import AgentManifest

manifest = AgentManifest(
    id="qapilot",
    title="QAPilot",
    description="7-layer QA review for SEO deliverables — accuracy, on-page, content, AI detection, visual, strategy, consistency.",
    version="1.0.0",
    route_prefix="/api/agents/qa",
    icon="🔍",
    category="quality",
    owner="matthew",
    tags=("qa", "review", "content"),
)
