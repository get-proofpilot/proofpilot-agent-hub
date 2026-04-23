"""
Service Page pipeline configuration.

Service pages target "[service] [city]" keywords and are built to
rank locally and convert at 8%+. They follow a mandatory conversion
architecture: hero → trust → scope → pricing → process → local → FAQ → CTA.
"""

PAGE_CONFIG = {
    "id": "service-page",
    "title": "Service Page",
    "description": "Conversion-optimized service page targeting high-intent local keywords",
    "stages": ["research", "strategy", "copywrite", "design", "images", "qa"],
    "research_focus": "commercial_intent",
    "content_target": "800-1200 words",

    "required_inputs": ["domain", "service", "location"],
    "optional_inputs": ["differentiators", "price_range", "competitors", "notes"],

    "input_schema": {
        "domain": {"label": "Client Domain", "placeholder": "saiyanelectric.com", "type": "text"},
        "service": {"label": "Service", "placeholder": "panel upgrade", "type": "text"},
        "location": {"label": "Location", "placeholder": "Chandler, AZ", "type": "text"},
        "differentiators": {"label": "Differentiators", "placeholder": "same-day service, master electrician", "type": "text"},
        "price_range": {"label": "Price Range", "placeholder": "$1,200-$3,500", "type": "text"},
        "competitors": {"label": "Competitors", "placeholder": "comp1.com, comp2.com", "type": "text"},
        "notes": {"label": "Notes", "placeholder": "Any specific instructions", "type": "textarea"},
    },
}
