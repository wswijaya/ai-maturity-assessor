"""
Unit tests for src/agent/scorer.py.
Run with: python3 -m pytest tests/test_scorer.py -v
"""

import json
from unittest.mock import Mock

import pytest

from src.agent.scorer import score_dimension
from src.llm.base import LLMClient
from src.models.assessment import DimensionAssessment, DimensionID


@pytest.fixture
def active_dim() -> DimensionAssessment:
    """A DimensionAssessment in its initial unclosed state."""
    return DimensionAssessment(
        dimension_id=DimensionID.STRATEGY,
        label="Strategy & Vision",
    )


def _make_client(response_text: str) -> LLMClient:
    """Return a mock LLMClient whose complete() returns response_text."""
    client = Mock(spec=LLMClient)
    client.complete.return_value = response_text
    return client


def test_empty_evidence_raises_before_close(active_dim):
    """
    When the LLM returns a valid JSON block with an empty evidence list,
    score_dimension must raise ValueError and must not call dim.close()
    (verified by checking dim.is_complete remains False).
    """
    response = json.dumps({
        "score": 3,
        "rationale": "The organisation has an informal AI strategy.",
        "evidence": [],
        "gaps": ["No documented roadmap"],
    })
    client = _make_client(response)

    with pytest.raises(ValueError, match="[Ee]vidence"):
        score_dimension(active_dim, [], client, "system")

    assert not active_dim.is_complete
