"""Smoke tests for StrategyPilot prompt loader."""
from agents.strategypilot.prompts import (
    FOOTPRINT_SYSTEM,
    COMPETITIVE_SYSTEM,
    PAGE_SYSTEMS_SYSTEM,
    ROI_SYSTEM,
    SYNTHESIS_SYSTEM,
)


def test_all_prompts_non_empty():
    for p in (FOOTPRINT_SYSTEM, COMPETITIVE_SYSTEM, PAGE_SYSTEMS_SYSTEM, ROI_SYSTEM, SYNTHESIS_SYSTEM):
        assert len(p) > 500


def test_page_systems_covers_12_categories():
    # Prompt should mention categories A through L (12 page-system types)
    for letter in "ABCDEFGHIJKL":
        assert f"\n{letter}." in PAGE_SYSTEMS_SYSTEM
