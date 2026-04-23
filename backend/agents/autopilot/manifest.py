"""AutoPilot AI manifest."""
from agents._template.manifest import AgentManifest

manifest = AgentManifest(
    id="autopilot",
    title="AutoPilot AI",
    description="6-stage SEO page builder — research, strategy, copywrite, design, images, QA with revision loop.",
    version="1.0.0",
    route_prefix="/api/pipeline",
    icon="✈️",
    category="production",
    owner="matthew",
    tags=("autopilot", "seo", "pages", "content", "images"),
)
