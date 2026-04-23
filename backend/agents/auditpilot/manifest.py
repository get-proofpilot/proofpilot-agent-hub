"""AuditPilot manifest."""
from agents._template.manifest import AgentManifest

manifest = AgentManifest(
    id="auditpilot",
    title="AuditPilot",
    description="Multi-stage sales audit — Firecrawl + DataForSEO + Strategic Brain + Sales Audit v2 document.",
    version="1.0.0",
    route_prefix="/api/agents/audit",
    icon="📊",
    category="sales",
    owner="matthew",
    tags=("audit", "sales", "prospect", "seo"),
)
