"""Smoke tests for AuditPilot prompt loader."""
from agents.auditpilot.prompts import (
    SITE_ANALYSIS_SYSTEM,
    RANKING_REALITY_SYSTEM,
    STRATEGIC_BRAIN_SYSTEM,
    SYNTHESIS_SYSTEM,
)


def test_all_prompts_non_empty():
    assert len(SITE_ANALYSIS_SYSTEM) > 500
    assert len(RANKING_REALITY_SYSTEM) > 500
    assert len(STRATEGIC_BRAIN_SYSTEM) > 500
    assert len(SYNTHESIS_SYSTEM) > 500


def test_strategic_brain_has_eight_dimensions():
    for i in range(1, 9):
        assert f"{i}." in STRATEGIC_BRAIN_SYSTEM
