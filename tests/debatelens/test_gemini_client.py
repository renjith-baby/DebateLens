from unittest.mock import MagicMock, patch

import pytest

from debatelens.analysis.gemini_client import GeminiClient, GeminiConfig


@pytest.fixture
def gemini_config():
    return GeminiConfig(
        api_key="test-key",
        model_fast="gemini-2.0-flash",
        model_pro="gemini-2.5-pro",
    )


def test_generate_json_returns_parsed_dict(gemini_config):
    fake_resp = MagicMock()
    fake_resp.text = '{"key": "value"}'
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_resp

    with patch("debatelens.analysis.gemini_client.genai.Client", return_value=fake_client):
        c = GeminiClient(gemini_config)
        result = c.generate_json(model="gemini-2.0-flash", prompt="hello")

    assert result == {"key": "value"}


def test_generate_json_strips_code_fence(gemini_config):
    fake_resp = MagicMock()
    fake_resp.text = "```json\n{\"k\": 1}\n```"
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_resp

    with patch("debatelens.analysis.gemini_client.genai.Client", return_value=fake_client):
        c = GeminiClient(gemini_config)
        result = c.generate_json(model="gemini-2.0-flash", prompt="x")

    assert result == {"k": 1}


def test_generate_json_retries_on_invalid_json(gemini_config):
    bad = MagicMock()
    bad.text = "not json"
    good = MagicMock()
    good.text = '{"ok": true}'
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = [bad, good]

    with patch("debatelens.analysis.gemini_client.genai.Client", return_value=fake_client):
        c = GeminiClient(gemini_config)
        result = c.generate_json(model="gemini-2.0-flash", prompt="x")

    assert result == {"ok": True}
    assert fake_client.models.generate_content.call_count == 2


def test_generate_with_search_passes_tools(gemini_config):
    fake_resp = MagicMock()
    fake_resp.text = '{"verdict": "true"}'
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_resp

    with patch("debatelens.analysis.gemini_client.genai.Client", return_value=fake_client):
        c = GeminiClient(gemini_config)
        result = c.generate_json(model="gemini-2.5-pro", prompt="x", with_search=True)

    assert result == {"verdict": "true"}
    call = fake_client.models.generate_content.call_args
    config = call.kwargs.get("config")
    assert config is not None
    assert getattr(config, "tools", None), "tools should be set when with_search=True"
