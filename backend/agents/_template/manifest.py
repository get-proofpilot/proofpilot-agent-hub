"""Agent manifest — metadata the Agent Hub reads at boot.

Every Pilot has exactly one manifest. The auto-discovery loader
(backend/agents/__init__.py) imports this, mounts the router, and
exposes the manifest to the frontend for sidebar rendering.
"""
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class AgentManifest:
    id: str
    title: str
    description: str
    version: str
    route_prefix: str
    icon: str = ""
    category: str = "agent"
    owner: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return asdict(self)


# Replace these values when cloning the template.
manifest = AgentManifest(
    id="template",
    title="Template Pilot",
    description="Reference skeleton — do not mount in production.",
    version="0.0.0",
    route_prefix="/api/agents/_template",
    icon="📄",
    category="internal",
    owner="platform",
    tags=("template",),
)
