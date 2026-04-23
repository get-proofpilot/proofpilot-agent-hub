"""
Gemini Pro page design engine.

Alternative to Claude for the design stage — Gemini Pro excels at
HTML/CSS generation with more refined visual output. Can be used
as a drop-in replacement or alongside Claude for A/B testing.
"""

import logging
import os
from typing import Optional

import google.generativeai as genai

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def _get_model():
    """Initialize Gemini Pro model."""
    key = GEMINI_API_KEY
    if not key:
        raise ValueError("GEMINI_API_KEY not set")
    genai.configure(api_key=key)
    return genai.GenerativeModel("gemini-2.5-pro")


async def generate_page_gemini(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 65536,
) -> str:
    """Generate a full HTML page using Gemini Pro.

    Returns the raw HTML string (no streaming — Gemini returns complete response).
    """
    model = _get_model()

    response = model.generate_content(
        [
            {"role": "user", "parts": [{"text": f"{system_prompt}\n\n---\n\n{user_prompt}"}]},
        ],
        generation_config=genai.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=0.7,
        ),
    )

    text = response.text
    # Strip markdown code fences if Gemini wrapped the HTML
    if text.strip().startswith("```html"):
        text = text.strip().removeprefix("```html").removesuffix("```").strip()
    elif text.strip().startswith("```"):
        text = text.strip().removeprefix("```").removesuffix("```").strip()

    return text
