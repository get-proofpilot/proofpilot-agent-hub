"""
Typed artifacts passed between pipeline stages.

Each stage produces an artifact that the next stage consumes. Artifacts are
serialized to JSON for SQLite persistence (pause/resume across approval gates).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ResearchArtifact:
    """Output of the RESEARCH stage — raw SEO data and analysis."""
    domain: str = ""
    service: str = ""
    location: str = ""

    # Keyword data from DataForSEO
    keywords: list[dict] = field(default_factory=list)
    keyword_volumes: list[dict] = field(default_factory=list)
    keyword_difficulty: list[dict] = field(default_factory=list)

    # Competitor data
    competitors: list[dict] = field(default_factory=list)
    competitor_keywords: list[dict] = field(default_factory=list)

    # SERP data
    serp_results: list[dict] = field(default_factory=list)
    ai_overview_data: list[dict] = field(default_factory=list)

    # Content gaps identified
    content_gaps: list[str] = field(default_factory=list)

    # Backlink context
    backlink_summary: dict = field(default_factory=dict)

    # Trend data
    trends: list[dict] = field(default_factory=list)

    # Raw analysis text from Claude (the research report)
    analysis_text: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> ResearchArtifact:
        return cls(**json.loads(data))

    def as_prompt_context(self) -> str:
        """Format research data for injection into the next stage's prompt."""
        parts = []
        if self.keywords:
            top = self.keywords[:20]
            parts.append(f"## Top Keywords ({len(self.keywords)} total)\n" +
                         "\n".join(f"- {kw.get('keyword', '')} (vol: {kw.get('volume', 'N/A')}, "
                                   f"KD: {kw.get('difficulty', 'N/A')})"
                                   for kw in top))
        if self.competitors:
            parts.append(f"## Competitors ({len(self.competitors)})\n" +
                         "\n".join(f"- {c.get('domain', '')} (visibility: {c.get('visibility', 'N/A')})"
                                   for c in self.competitors[:5]))
        if self.content_gaps:
            parts.append("## Content Gaps\n" + "\n".join(f"- {g}" for g in self.content_gaps[:10]))
        if self.ai_overview_data:
            parts.append(f"## AI Overview Presence\n{len(self.ai_overview_data)} keywords trigger AI Overviews")
        if self.analysis_text:
            parts.append(f"## Full Research Analysis\n{self.analysis_text}")
        return "\n\n".join(parts)


@dataclass
class StrategyArtifact:
    """Output of the STRATEGY stage — content brief and page structure."""
    page_type: str = ""
    target_keyword: str = ""
    secondary_keywords: list[str] = field(default_factory=list)
    search_intent: str = ""

    # Page structure
    heading_hierarchy: list[dict] = field(default_factory=list)  # [{level, text, word_target}]
    content_sections: list[dict] = field(default_factory=list)   # [{heading, description, word_count}]
    total_word_target: int = 0

    # SEO specifications
    title_tag: str = ""
    meta_description: str = ""
    internal_links: list[dict] = field(default_factory=list)  # [{anchor, url, context}]
    schema_types: list[str] = field(default_factory=list)

    # Content brief
    angle: str = ""
    differentiators: list[str] = field(default_factory=list)
    cta_strategy: str = ""
    faq_questions: list[str] = field(default_factory=list)

    # Full brief text from Claude
    brief_text: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> StrategyArtifact:
        return cls(**json.loads(data))

    def as_prompt_context(self) -> str:
        parts = [f"## Content Brief: {self.page_type}"]
        parts.append(f"Target keyword: {self.target_keyword}")
        parts.append(f"Search intent: {self.search_intent}")
        parts.append(f"Word target: {self.total_word_target}")
        if self.title_tag:
            parts.append(f"Title tag: {self.title_tag}")
        if self.meta_description:
            parts.append(f"Meta description: {self.meta_description}")
        if self.heading_hierarchy:
            parts.append("### Page Structure")
            for h in self.heading_hierarchy:
                indent = "  " * (h.get("level", 2) - 1)
                parts.append(f"{indent}- H{h.get('level', 2)}: {h.get('text', '')} "
                             f"(~{h.get('word_target', 0)} words)")
        if self.faq_questions:
            parts.append("### FAQ Questions")
            for q in self.faq_questions:
                parts.append(f"- {q}")
        if self.differentiators:
            parts.append("### Differentiators")
            for d in self.differentiators:
                parts.append(f"- {d}")
        if self.cta_strategy:
            parts.append(f"### CTA Strategy\n{self.cta_strategy}")
        if self.brief_text:
            parts.append(f"### Full Brief\n{self.brief_text}")
        return "\n".join(parts)


@dataclass
class ContentArtifact:
    """Output of the COPYWRITE stage — the actual page content."""
    markdown: str = ""
    word_count: int = 0

    # SEO elements
    title_tag: str = ""
    meta_description: str = ""
    h1: str = ""

    # Structured data
    schema_json: str = ""
    faq_data: list[dict] = field(default_factory=list)  # [{question, answer}]

    # Internal linking applied
    internal_links_used: list[dict] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> ContentArtifact:
        return cls(**json.loads(data))

    def as_prompt_context(self) -> str:
        parts = [f"## Page Content ({self.word_count} words)"]
        if self.title_tag:
            parts.append(f"Title: {self.title_tag}")
        if self.meta_description:
            parts.append(f"Meta: {self.meta_description}")
        parts.append(f"\n{self.markdown}")
        if self.schema_json:
            parts.append(f"\n## Schema JSON-LD\n```json\n{self.schema_json}\n```")
        return "\n".join(parts)


@dataclass
class DesignArtifact:
    """Output of the DESIGN stage — production HTML/CSS."""
    html: str = ""
    css: str = ""
    full_page: str = ""  # Complete HTML document with embedded CSS

    # Image specifications for later generation
    image_prompts: list[dict] = field(default_factory=list)  # [{slot, alt_text, prompt, size}]

    # WordPress integration hints
    wp_template_suggestion: str = ""
    wp_class_map: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> DesignArtifact:
        return cls(**json.loads(data))


@dataclass
class QAArtifact:
    """Output of the QA stage — quality scores and recommendations."""
    overall_score: int = 0  # 0-100

    # Category scores (matches blog-analyze 5-category system)
    content_quality_score: int = 0
    seo_score: int = 0
    eeat_score: int = 0
    technical_score: int = 0
    aeo_score: int = 0  # AI Engine Optimization / citability

    # Issues found
    issues: list[dict] = field(default_factory=list)  # [{severity, category, description, fix}]

    # Pass/fail
    approved: bool = False
    approval_reason: str = ""

    # Recommendations
    recommendations: list[str] = field(default_factory=list)

    # Full review text
    review_text: str = ""

    # Structured revision directives (parsed from REVISION_DIRECTIVES block)
    revision_directives: list[dict] = field(default_factory=list)  # [{stage, action, instruction}]

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> QAArtifact:
        d = json.loads(data)
        # Handle older artifacts that don't have revision_directives
        if "revision_directives" not in d:
            d["revision_directives"] = []
        return cls(**d)

    def get_directives_for_stage(self, stage: str) -> list[dict]:
        """Get revision directives targeted at a specific stage."""
        return [d for d in self.revision_directives if d.get("stage") == stage]

    def has_directives(self) -> bool:
        return len(self.revision_directives) > 0


# Maps stage names to their artifact types for deserialization
ARTIFACT_TYPES = {
    "research": ResearchArtifact,
    "strategy": StrategyArtifact,
    "copywrite": ContentArtifact,
    "design": DesignArtifact,
    "qa": QAArtifact,
}
