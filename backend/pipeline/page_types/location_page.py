"""
Location Page pipeline configuration.

Location pages target "[service] in [city]" and nearby-city searches.
Focus: local proof, service area coverage, city-specific context.
"""

PAGE_CONFIG = {
    "id": "location-page",
    "title": "Location Page",
    "description": "Local SEO page targeting city-specific service searches",
    "stages": ["research", "strategy", "copywrite", "design", "images", "qa"],
    "research_focus": "local_intent",
    "content_target": "600-1000 words",

    "required_inputs": ["domain", "primary_service", "target_location"],
    "optional_inputs": ["home_base", "local_details", "services_list", "competitors", "notes"],

    "input_schema": {
        "domain": {"label": "Client Domain", "placeholder": "saiyanelectric.com", "type": "text"},
        "primary_service": {"label": "Primary Service", "placeholder": "electrician", "type": "text"},
        "target_location": {"label": "Target City", "placeholder": "Mesa, AZ", "type": "text"},
        "home_base": {"label": "Home Base City", "placeholder": "Chandler, AZ", "type": "text"},
        "local_details": {"label": "Local Details", "placeholder": "Neighborhoods, landmarks, local context", "type": "textarea"},
        "services_list": {"label": "Services Offered", "placeholder": "panel upgrade, rewiring, EV charger install", "type": "text"},
        "competitors": {"label": "Competitors", "placeholder": "comp1.com, comp2.com", "type": "text"},
        "notes": {"label": "Notes", "placeholder": "Any specific instructions", "type": "textarea"},
    },
}
