"""
tests/test_explainer.py
========================
Verifies msa_toolkit.explainer.generate_narrative(): skips gracefully
without ANTHROPIC_API_KEY, and returns the model's text when the
Claude API call succeeds. The API call itself is mocked -- no network.
"""

from unittest.mock import MagicMock, patch

from msa_toolkit.explainer import generate_narrative

SAMPLE_PAYLOAD = {
    "schema_version": 1,
    "study_type": "crossed",
    "metrics": {"status": "MARGINAL", "pct_grr": 18.4},
}


def test_generate_narrative_skips_without_api_key(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = generate_narrative(SAMPLE_PAYLOAD)
    assert result is None
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out


def test_generate_narrative_returns_model_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="This gauge is MARGINAL because...")]

    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create.return_value = fake_response
        result = generate_narrative(SAMPLE_PAYLOAD)

    assert result == "This gauge is MARGINAL because..."
    mock_anthropic.return_value.messages.create.assert_called_once()
