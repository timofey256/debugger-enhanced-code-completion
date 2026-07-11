import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Any

import yaml
from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from libs.llm.patch_utils import extract_unified_diff
from libs.llm.tooling import (
    ToolCatalog,
    ToolSessionContext,
    parse_tool_invocation_from_call,
)
from libs.prompts.resources import load_prompt

_RETRYABLE_ERRORS = (
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
)
_MAX_RETRIES = 10
_BASE_RETRY_DELAY = 2.0
_MAX_RETRY_DELAY = 60.0
_RETRY_JITTER = 1.0


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    ms = headers.get("retry-after-ms")
    if ms:
        try:
            return float(ms) / 1000.0
        except (TypeError, ValueError):
            pass
    secs = headers.get("retry-after")
    if secs:
        try:
            return float(secs)
        except (TypeError, ValueError):
            pass
    return None


def create_chat_completion(client: OpenAI, **create_kwargs: Any):
    attempt = 0
    while True:
        try:
            return client.chat.completions.create(**create_kwargs)
        except _RETRYABLE_ERRORS as exc:
            attempt += 1
            if attempt > _MAX_RETRIES:
                logger.error(
                    "LLM call failed after %d retries: %s", _MAX_RETRIES, exc
                )
                raise
            backoff = min(_MAX_RETRY_DELAY, _BASE_RETRY_DELAY * (2 ** (attempt - 1)))
            hinted = _retry_after_seconds(exc) or 0.0
            delay = min(_MAX_RETRY_DELAY, max(backoff, hinted)) + random.uniform(0.0, _RETRY_JITTER)
            logger.warning(
                "LLM %s (attempt %d/%d); retrying in %.2fs",
                type(exc).__name__,
                attempt,
                _MAX_RETRIES,
                delay,
            )
            time.sleep(delay)


@dataclass
class ToolSessionResult:
    patch: str
    transcript: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    tool_call_counts: dict[str, int] = field(default_factory=dict)

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
        self._client = OpenAI(
            api_key=api_key,
            base_url=provider_cfg["base_url"],
            max_retries=0,
        )

    def complete_code(self, prompt: str, max_tokens: int = 2000) -> ToolSessionResult:
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
        response = create_chat_completion(
            self._client,
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            **kwargs,
        )
        logger.info(
            "Received response from provider=%s model=%s",
            self._provider, self._model,
        )
        usage = response.usage
        input_tokens = 0
        output_tokens = 0
        if usage is None:
            logger.warning("No usage data in response from complete_code provider=%s model=%s", self._provider, self._model)
        else:
            input_tokens = usage.prompt_tokens or 0
            output_tokens = usage.completion_tokens or 0
        return ToolSessionResult(
            patch=str(response.choices[0].message.content),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def complete_with_tools(
        self,
        prompt: str,
        *,
        catalog: ToolCatalog,
        context: ToolSessionContext,
        max_tool_turns: int = 35,
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
        _input_tokens = 0
        _output_tokens = 0
        _tool_call_counts: dict[str, int] = {}

        for turn in range(self._max_tool_turns):
            is_last_turn = turn == self._max_tool_turns - 1
            if is_last_turn:
                patch_requirements = load_prompt("strict_patch_requirements.txt").strip()
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
            response = create_chat_completion(self._client, **create_kwargs)
            usage = response.usage
            if usage is None:
                logger.warning("tool-session turn=%d: no usage data in response", turn)
            else:
                _input_tokens += usage.prompt_tokens or 0
                _output_tokens += usage.completion_tokens or 0
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
                    return ToolSessionResult(patch=patch, transcript=messages, input_tokens=_input_tokens, output_tokens=_output_tokens, tool_call_counts=_tool_call_counts)
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
                _tool_call_counts[result.name] = _tool_call_counts.get(result.name, 0) + 1
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
                    return ToolSessionResult(patch=result.patch, transcript=messages, input_tokens=_input_tokens, output_tokens=_output_tokens, tool_call_counts=_tool_call_counts)

        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                patch = extract_unified_diff(msg.get("content") or "")
                if patch:
                    return ToolSessionResult(patch=patch, transcript=messages, input_tokens=_input_tokens, output_tokens=_output_tokens, tool_call_counts=_tool_call_counts)

        forced_patch, used_in, used_out = self._request_final_patch(messages)
        _input_tokens += used_in
        _output_tokens += used_out
        if forced_patch:
            return ToolSessionResult(patch=forced_patch, transcript=messages, input_tokens=_input_tokens, output_tokens=_output_tokens, tool_call_counts=_tool_call_counts)

        logger.warning(
            "Tool session exhausted %d turns without final apply_patch",
            self._max_tool_turns,
        )
        return ToolSessionResult(patch="", transcript=messages, input_tokens=_input_tokens, output_tokens=_output_tokens, tool_call_counts=_tool_call_counts)

    def _request_final_patch(self, messages: list[dict[str, Any]]) -> tuple[str, int, int]:
        patch_requirements = load_prompt("strict_patch_requirements.txt").strip()
        investigation = self._render_investigation(messages)
        clean_messages = [
            {
                "role": "system",
                "content": (
                    "You are a software engineer. Output ONLY a unified git diff "
                    "that fixes the described bug. Do not call tools. Do not write "
                    "explanations or markdown fences."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{investigation}\n\n"
                    "Using the investigation above, output the COMPLETE unified "
                    "git diff that fixes the bug now. If uncertain, still output "
                    "your single best-guess diff.\n\n"
                    f"{patch_requirements}"
                ),
            },
        ]
        try:
            response = create_chat_completion(
                self._client,
                model=self._model,
                messages=clean_messages,
                max_completion_tokens=self._max_tokens,
                **self._extra_kwargs(),
            )
        except Exception as exc:
            logger.warning("final patch extraction request failed: %s", exc)
            return "", 0, 0
        usage = response.usage
        used_in = (usage.prompt_tokens or 0) if usage else 0
        used_out = (usage.completion_tokens or 0) if usage else 0
        content = response.choices[0].message.content or ""
        messages.append({"role": "assistant", "content": content})
        return extract_unified_diff(content), used_in, used_out

    @staticmethod
    def _render_investigation(messages: list[dict[str, Any]], max_chars: int = 40000) -> str:
        task = ""
        body: list[str] = []
        for msg in messages:
            content = msg.get("content") or ""
            role = msg.get("role")
            if role == "user" and not task:
                task = content
            elif role == "assistant" and content.strip():
                body.append("## Analysis\n" + content)
            elif role == "tool" and content.strip():
                body.append("## Evidence\n" + content)
        tail: list[str] = []
        used = 0
        for chunk in reversed(body):
            if used + len(chunk) > max_chars:
                break
            tail.append(chunk)
            used += len(chunk)
        tail.reverse()
        return "## Task\n" + task + "\n\n" + "\n\n".join(tail)

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
