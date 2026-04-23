"""RedditPilot manifest."""
from agents._template.manifest import AgentManifest

manifest = AgentManifest(
    id="redditpilot",
    title="RedditPilot",
    description="Reddit outreach engine — subreddit scanning, opportunity discovery, human-in-the-loop content generation, A/B testing, learning loop.",
    version="1.0.0",
    route_prefix="/api/reddit",
    icon="🗯️",
    category="outreach",
    owner="matthew",
    tags=("reddit", "outreach", "community", "a-b-testing"),
)
