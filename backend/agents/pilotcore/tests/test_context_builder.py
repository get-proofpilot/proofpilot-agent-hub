"""Smoke tests for Pilot Core context builder."""
from agents.pilotcore.context_builder import build_context


def test_build_context_returns_shape():
    ctx = build_context()
    assert "clients" in ctx
    assert "total_clients" in ctx
    assert "overdue_clients" in ctx
    assert "attention_clients" in ctx
    assert "team_workload" in ctx
