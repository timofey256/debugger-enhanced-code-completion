import json
import logging
import os
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Any

import yaml
from dotenv import load_dotenv
from openai import OpenAI

from libs.llm.patch_utils import extract_unified_diff
from libs.llm.tooling import (
    ToolCatalog,
    ToolSessionContext,
    parse_tool_invocation_from_call,
)
from libs.prompts.resources import load_prompt


@dataclass
class ToolSessionResult:
    patch: str
    transcript: list[dict[str, Any]] = field(default_factory=list)

    def render(self) -> str:
        lines: list[str] = []
        for entry in self.transcript:
            role = entry.get("role", "?")
            lines.append(f"=== {role} ===")
            content = entry.get("content")
            if content:
                lines.append(content)
            for tc in entry.get("tool_calls", []) or []:
                fn = tc.get("function", {})
                lines.append(
                    f"[tool_call id={tc.get('id', '')} name={fn.get('name', '')}]"
                )
                lines.append(fn.get("arguments", ""))
            tool_call_id = entry.get("tool_call_id")
            if tool_call_id:
                lines.append(f"[tool_call_id={tool_call_id}]")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


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

    def complete_with_tools(
        self,
        prompt: str,
        *,
        catalog: ToolCatalog,
        context: ToolSessionContext,
        max_tool_turns: int = 10,
        max_tokens: int = 2000,
        max_tool_output_chars: int = 20000,
    ) -> ToolSessionResult:
        runner = _ToolSessionRunner(
            client=self._client,
            model=self._model,
            model_options=self._model_options,
            catalog=catalog,
            context=context,
            max_tool_turns=max_tool_turns,
            max_tokens=max_tokens,
            max_tool_output_chars=max_tool_output_chars,
        )
        return runner.run(prompt)


class _ToolSessionRunner:
    def __init__(
        self,
        *,
        client: OpenAI,
        model: str,
        model_options: dict,
        catalog: ToolCatalog,
        context: ToolSessionContext,
        max_tool_turns: int,
        max_tokens: int,
        max_tool_output_chars: int,
    ):
        if max_tool_turns < 1:
            raise ValueError("max_tool_turns must be >= 1")
        self._client = client
        self._model = model
        self._model_options = model_options
        self._catalog = catalog
        self._context = context
        self._max_tool_turns = max_tool_turns
        self._max_tokens = max_tokens
        self._max_tool_output_chars = max_tool_output_chars

    def run(self, prompt: str) -> ToolSessionResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_message()},
            {"role": "user", "content": prompt},
        ]
        tools = self._catalog.openai_tools()

        for turn in range(self._max_tool_turns):
            is_last_turn = turn == self._max_tool_turns - 1
            if is_last_turn:
                patch_requirements = load_prompt("swebench/strict_patch_requirements.txt").strip()
                messages.append({
                    "role": "user",
                    "content": (
                        "This is your final tool turn. You MUST call apply_patch "
                        "now with a complete unified git diff. No other tool calls "
                        "and no prose are allowed.\n\n"
                        f"{patch_requirements}"
                    ),
                })
            create_kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "tools": tools,
                "max_completion_tokens": self._max_tokens,
                **self._extra_kwargs(),
            }
            if is_last_turn:
                create_kwargs["tool_choice"] = {
                    "type": "function",
                    "function": {"name": "apply_patch"},
                }
            response = self._client.chat.completions.create(**create_kwargs)
            choice = response.choices[0].message
            tool_calls = list(getattr(choice, "tool_calls", None) or [])
            content_text = choice.content or ""
            reasoning_content = getattr(choice, "reasoning_content", None)
            logger.debug(choice)

            assistant_msg: dict[str, Any] = {"role": "assistant", "content": content_text}
            if reasoning_content:
                assistant_msg["reasoning_content"] = reasoning_content
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)
            logger.info(
                "tool-session turn=%d role=assistant tool_calls=%d content_len=%d",
                turn, len(tool_calls), len(content_text),
            )

            if not tool_calls:
                patch = extract_unified_diff(content_text)
                if patch:
                    return ToolSessionResult(patch=patch, transcript=messages)
                if not is_last_turn:
                    nudge = (
                        "Submit your final fix using the apply_patch tool with a "
                        "complete unified git diff. Do not return prose."
                    )
                    messages.append({"role": "user", "content": nudge})

            for tc in tool_calls:
                try:
                    invocation = parse_tool_invocation_from_call(tc)
                except (ValueError, json.JSONDecodeError) as exc:
                    logger.warning(
                        "tool-session turn=%d bad tool_call id=%s: %s",
                        turn, tc.id, exc,
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": f"Error: malformed tool call – {exc}. Please retry with valid JSON arguments.",
                    })
                    continue
                result = self._catalog.execute(self._context, invocation)
                tool_output = result.to_string(max_chars=self._max_tool_output_chars)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": result.name,
                    "content": tool_output,
                })
                logger.info(
                    "tool-session turn=%d tool=%s status=%s output_len=%d",
                    turn, result.name, result.status, len(result.output),
                )
                if (
                    result.name == "apply_patch"
                    and result.status == "ok"
                    and result.patch
                ):
                    return ToolSessionResult(patch=result.patch, transcript=messages)

        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                patch = extract_unified_diff(msg.get("content") or "")
                if patch:
                    return ToolSessionResult(patch=patch, transcript=messages)
        logger.warning(
            "Tool session exhausted %d turns without final apply_patch",
            self._max_tool_turns,
        )
        return ToolSessionResult(patch="", transcript=messages)

    def _extra_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if "reasoning_effort" in self._model_options:
            kwargs["reasoning_effort"] = self._model_options["reasoning_effort"]
        if self._model_options.get("thinking"):
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        return kwargs

    def _system_message(self) -> str:
        names = [s.name for s in self._catalog.specs()]
        tool_list = ", ".join(names) if names else "(no tools available)"
        return (
            "You can call the following tools to inspect the project and runtime "
            "before submitting a fix: "
            f"{tool_list}. "
            "Issue tool calls to gather evidence. Tool outputs are bounded; "
            "request specific files and line ranges. "
            "When you are ready, call apply_patch with a complete unified git diff "
            "to submit the fix and end the session. "
            f"You have at most {self._max_tool_turns} tool turns."
        )
