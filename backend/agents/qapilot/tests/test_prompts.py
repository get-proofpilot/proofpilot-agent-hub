"""Smoke tests for QAPilot prompt loader."""
from agents.qapilot.prompts import QA_SYSTEM, QA_CONTENT_ONLY, load_prompt


def test_prompts_non_empty():
    assert len(QA_SYSTEM) > 500
    assert len(QA_CONTENT_ONLY) > 100


def test_prompts_mention_seven_layers():
    assert "Layer 7" in QA_SYSTEM


def test_load_prompt_missing_raises():
    import pytest
    with pytest.raises(FileNotFoundError):
        load_prompt("does_not_exist")
