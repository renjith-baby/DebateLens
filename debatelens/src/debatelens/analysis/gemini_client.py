from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from google import genai
from google.genai import types as gtypes


logger = logging.getLogger(__name__)

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


@dataclass
class GeminiConfig:
    api_key: str
    model_fast: str = "gemini-2.0-flash"
    model_pro: str = "gemini-2.5-pro"
    max_retries: int = 2


class GeminiClient:
    def __init__(self, config: GeminiConfig) -> None:
        self._config = config
        self._client = genai.Client(api_key=config.api_key)

    def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        with_search: bool = False,
        temperature: float = 0.0,
    ) -> dict | list:
        config_kwargs: dict = {"temperature": temperature}
        if with_search:
            config_kwargs["tools"] = [gtypes.Tool(google_search=gtypes.GoogleSearch())]
        else:
            config_kwargs["response_mime_type"] = "application/json"
        config = gtypes.GenerateContentConfig(**config_kwargs)

        last_err: Exception | None = None
        current_prompt = prompt
        for attempt in range(self._config.max_retries + 1):
            resp = self._client.models.generate_content(
                model=model,
                contents=current_prompt,
                config=config,
            )
            text = (resp.text or "").strip()
            stripped = _strip_fence(text)
            try:
                return json.loads(stripped)
            except json.JSONDecodeError as e:
                last_err = e
                logger.warning("gemini returned non-JSON (attempt %s): %s", attempt + 1, text[:200])
                current_prompt = (
                    f"{prompt}\n\nYour previous response was not valid JSON. "
                    "Return ONLY the JSON object, no prose, no code fences."
                )

        raise RuntimeError(f"gemini failed to produce valid JSON: {last_err}")


def _strip_fence(text: str) -> str:
    m = _FENCE.match(text.strip())
    return m.group(1) if m else text
