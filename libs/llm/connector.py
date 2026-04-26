import logging
import os
from importlib.resources import files

import yaml
from dotenv import load_dotenv
from openai import OpenAI


_CONFIG_FILENAME = "llm_providers.yaml"

logger = logging.getLogger(__name__)


def _load_config():
    text = files(__package__).joinpath(_CONFIG_FILENAME).read_text(encoding="utf-8")
    return yaml.safe_load(text)["providers"]


class LLMConnector:
    def __init__(self, provider: str, model: str):
        load_dotenv()
        providers = _load_config()

        if provider not in providers:
            raise ValueError(
                f"Unknown provider '{provider}'. Valid providers: {sorted(providers)}"
            )
        provider_cfg = providers[provider]

        models = provider_cfg.get("models") or {}
        if model not in models:
            raise ValueError(
                f"Unknown model '{model}' for provider '{provider}'. "
                f"Valid models: {sorted(models)}"
            )

        api_key_env = provider_cfg["api_key_env"]
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing env var {api_key_env}")

        self._provider = provider
        self._model = model
        self._model_options = models[model] or {}
        self._client = OpenAI(api_key=api_key, base_url=provider_cfg["base_url"])

    def complete_code(self, prompt: str, max_tokens: int = 2000) -> str:
        messages = [{"role": "user", "content": prompt}]
        kwargs = {}
        if "reasoning_effort" in self._model_options:
            kwargs["reasoning_effort"] = self._model_options["reasoning_effort"]
        if self._model_options.get("thinking"):
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        logger.info(
            "Sending request to provider=%s model=%s",
            self._provider, self._model,
        )
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            **kwargs,
        )
        logger.info(
            "Received response from provider=%s model=%s",
            self._provider, self._model,
        )
        return str(response.choices[0].message.content)
