"""
Blog Post pipeline configuration.

Blog posts target informational intent keywords: how-tos, cost guides,
comparison posts, "signs you need X" content. Longer format, focused
on topical authority and AI citability.
"""

PAGE_CONFIG = {
    "id": "blog-post",
    "title": "Blog Post",
    "description": "SEO blog post targeting informational keywords with AEO optimization",
    "stages": ["research", "strategy", "copywrite", "design", "images", "qa"],
    "research_focus": "informational_intent",
    "content_target": "1500-2500 words",

    "required_inputs": ["domain", "keyword", "business_type", "location"],
    "optional_inputs": ["audience", "tone", "internal_links", "competitors", "notes"],

    "input_schema": {
        "domain": {"label": "Client Domain", "placeholder": "saiyanelectric.com", "type": "text"},
        "keyword": {"label": "Target Keyword", "placeholder": "how much does it cost to rewire a house", "type": "text"},
        "business_type": {"label": "Business Type", "placeholder": "electrician", "type": "text"},
        "location": {"label": "Location", "placeholder": "Chandler, AZ", "type": "text"},
        "audience": {"label": "Audience", "placeholder": "homeowners", "type": "text"},
        "tone": {"label": "Tone", "placeholder": "conversational, expert", "type": "text"},
        "internal_links": {"label": "Internal Links", "placeholder": "URLs to link to", "type": "textarea"},
        "competitors": {"label": "Competitors", "placeholder": "comp1.com, comp2.com", "type": "text"},
        "notes": {"label": "Notes", "placeholder": "Any specific instructions", "type": "textarea"},
    },
}
