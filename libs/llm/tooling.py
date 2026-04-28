from __future__ import annotations

import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from libs.frames import ExecutionPathSerializer, Frame, FrameSerializer
from libs.harness.io_utils import render_numbered_range


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: Mapping[str, Any]

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": dict(self.parameters),
            },
        }


@dataclass(frozen=True)
class ToolInvocation:
    name: str
    arguments: Mapping[str, Any]
    tool_call_id: Optional[str] = None


@dataclass(frozen=True)
class ToolResult:
    name: str
    status: str
    output: str
    patch: Optional[str] = None

    def to_string(self, max_chars: Optional[int] = None) -> str:
        body = self.output
        if max_chars is not None and len(body) > max_chars:
            body = body[:max_chars]
        return (
            "<tool_result>\n"
            f"name={self.name}\n"
            f"status={self.status}\n"
            "output:\n"
            f"{body}\n"
            "</tool_result>"
        )


class ProjectPathResolver:
    def __init__(self, project_root: Path, container_project_root: str = "/testbed"):
        self._project_root = Path(project_root).resolve()
        self._container_project_root = Path(container_project_root).as_posix()

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def container_project_root(self) -> str:
        return self._container_project_root

    def resolve(self, raw_path: str) -> Path:
        value = str(raw_path).strip()
        if not value:
            raise ValueError("Path cannot be empty")

        candidate = Path(value)
        if candidate.is_absolute():
            posix = candidate.as_posix()
            if posix == self._container_project_root:
                resolved = self._project_root
            elif posix.startswith(self._container_project_root + "/"):
                rel = posix[len(self._container_project_root) + 1 :]
                resolved = self._project_root / rel
            elif str(candidate).startswith(str(self._project_root)):
                resolved = candidate
            else:
                raise ValueError(f"Path outside project root: {raw_path}")
        else:
            resolved = self._project_root / candidate

        final_path = resolved.resolve()
        if final_path != self._project_root and self._project_root not in final_path.parents:
            raise ValueError(f"Path outside project root: {raw_path}")
        return final_path

    def to_display(self, path: Path) -> str:
        resolved = path.resolve()
        rel = resolved.relative_to(self._project_root).as_posix()
        if rel:
            return f"{self._container_project_root}/{rel}"
        return self._container_project_root


@dataclass(frozen=True)
class ProjectToolContext:
    resolver: ProjectPathResolver
    source_map: Mapping[str, str]
    context_size: int


@dataclass(frozen=True)
class RuntimeToolContext:
    frames: Sequence[Frame]
    execution_path: Sequence[Frame]
    trace: Mapping[str, Any]
    test_output_path: Path


@dataclass(frozen=True)
class ToolSessionContext:
    project: ProjectToolContext
    runtime: Optional[RuntimeToolContext] = None


class BaseTool(ABC):
    def __init__(self, spec: ToolSpec):
        self.spec = spec

    @abstractmethod
    def execute(self, context: ToolSessionContext, invocation: ToolInvocation) -> ToolResult:
        raise NotImplementedError


class PrintProjectTreeTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolSpec(
                name="print_project_tree",
                description="Print project tree rooted at /testbed. Output contains folders and .py files only.",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            )
        )

    def execute(self, context: ToolSessionContext, invocation: ToolInvocation) -> ToolResult:
        root = context.project.resolver.project_root

        def _relative(path: Path) -> str:
            return path.relative_to(root).as_posix()

        entries: list[str] = []
        for path in root.rglob("*"):
            if path.is_dir():
                entries.append(_relative(path) + "/")
            elif path.is_file() and path.suffix == ".py":
                entries.append(_relative(path))

        return ToolResult(self.spec.name, "ok", "\n".join(entries))


class OpenFileTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolSpec(
                name="open_file",
                description="Read lines from a file under /testbed using start_line and end_line (inclusive).",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute /testbed path or path relative to /testbed.",
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "1-based start line.",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "1-based end line.",
                        },
                    },
                    "required": ["path", "start_line", "end_line"],
                    "additionalProperties": False,
                },
            )
        )

    def execute(self, context: ToolSessionContext, invocation: ToolInvocation) -> ToolResult:
        args = dict(invocation.arguments)
        path = str(args.get("path", "")).strip()
        if not path:
            return ToolResult(self.spec.name, "error", "Missing argument: path")

        try:
            start_line = self._to_positive_int(args.get("start_line"), "start_line")
            end_line = self._to_positive_int(args.get("end_line"), "end_line")
        except ValueError as exc:
            return ToolResult(self.spec.name, "error", str(exc))

        if end_line < start_line:
            return ToolResult(self.spec.name, "error", "end_line must be >= start_line")

        resolver = context.project.resolver
        try:
            file_path = resolver.resolve(path)
        except ValueError as exc:
            return ToolResult(self.spec.name, "error", str(exc))

        if not file_path.is_file():
            return ToolResult(self.spec.name, "error", f"File not found: {path}")

        source = file_path.read_text(encoding="utf-8", errors="replace")
        output = resolver.to_display(file_path) + "\n" + render_numbered_range(
            source, start_line, end_line
        )
        return ToolResult(self.spec.name, "ok", output)

    @staticmethod
    def _to_positive_int(value: Any, name: str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be an integer") from exc
        if parsed < 1:
            raise ValueError(f"{name} must be >= 1")
        return parsed


class SearchSymbolTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolSpec(
                name="search_symbol",
                description="Search symbol in /testbed Python files using grep -R -n --include=*.py.",
                parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Literal symbol to search.",
                        }
                    },
                    "required": ["symbol"],
                    "additionalProperties": False,
                },
            )
        )

    def execute(self, context: ToolSessionContext, invocation: ToolInvocation) -> ToolResult:
        symbol = str(invocation.arguments.get("symbol", "")).strip()
        if not symbol:
            return ToolResult(self.spec.name, "error", "Missing argument: symbol")

        root = context.project.resolver.project_root
        command = [
            "grep",
            "-R",
            "-n",
            "--include=*.py",
            "--",
            symbol,
            str(root),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode not in (0, 1):
            return ToolResult(self.spec.name, "error", result.stderr.strip())

        mapped: list[str] = []
        for line in result.stdout.splitlines():
            if line.startswith(str(root)):
                suffix = line[len(str(root)) :].lstrip("/")
                mapped.append(f"{context.project.resolver.container_project_root}/{suffix}")
            else:
                mapped.append(line)
        return ToolResult(self.spec.name, "ok", "\n".join(mapped))


class GetTestErrorTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolSpec(
                name="get_test_error",
                description="Return failing exception type and message from runtime trace.",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            )
        )

    def execute(self, context: ToolSessionContext, invocation: ToolInvocation) -> ToolResult:
        runtime = context.runtime
        if runtime is None:
            return ToolResult(self.spec.name, "error", "Runtime context is not available")

        exc_type = str(runtime.trace.get("exc_type", "")).strip()
        message = str(runtime.trace.get("message", "")).strip()
        return ToolResult(self.spec.name, "ok", f"Type: {exc_type}\nMessage: {message}")


class GetExecutionTraceTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolSpec(
                name="get_execution_trace",
                description="Serialize runtime execution path using ExecutionPathSerializer.",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            )
        )

    def execute(self, context: ToolSessionContext, invocation: ToolInvocation) -> ToolResult:
        runtime = context.runtime
        if runtime is None:
            return ToolResult(self.spec.name, "error", "Runtime context is not available")

        serializer = ExecutionPathSerializer()
        return ToolResult(self.spec.name, "ok", serializer.to_string(runtime.execution_path))


class GetFramesTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolSpec(
                name="get_frames",
                description="Serialize traceback frames using FrameSerializer with existing source context rendering.",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            )
        )

    def execute(self, context: ToolSessionContext, invocation: ToolInvocation) -> ToolResult:
        runtime = context.runtime
        if runtime is None:
            return ToolResult(self.spec.name, "error", "Runtime context is not available")

        serializer = FrameSerializer(
            source_map=context.project.source_map,
            context_size=context.project.context_size,
        )
        return ToolResult(self.spec.name, "ok", serializer.to_string_many(runtime.frames))


class GetVariableChangeTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolSpec(
                name="get_variable_change",
                description="Return variable value transitions over execution. This tool is currently unimplemented.",
                parameters={
                    "type": "object",
                    "properties": {
                        "variable_name": {
                            "type": "string",
                            "description": "Name of variable to inspect.",
                        }
                    },
                    "required": ["variable_name"],
                    "additionalProperties": False,
                },
            )
        )

    def execute(self, context: ToolSessionContext, invocation: ToolInvocation) -> ToolResult:
        return ToolResult(self.spec.name, "unimplemented", "get_variable_change is not implemented")


class ApplyPatchTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolSpec(
                name="apply_patch",
                description="Submit final code patch in unified diff format and finish the session.",
                parameters={
                    "type": "object",
                    "properties": {
                        "patch": {
                            "type": "string",
                            "description": "Unified diff patch text.",
                        }
                    },
                    "required": ["patch"],
                    "additionalProperties": False,
                },
            )
        )

    def execute(self, context: ToolSessionContext, invocation: ToolInvocation) -> ToolResult:
        patch = str(invocation.arguments.get("patch", "")).strip()
        if not patch:
            return ToolResult(self.spec.name, "error", "Missing argument: patch")
        normalized = patch + ("\n" if not patch.endswith("\n") else "")
        return ToolResult(self.spec.name, "ok", "Patch accepted", patch=normalized)


class ToolCatalog:
    def __init__(self, tools: Sequence[BaseTool]):
        self._tools = {tool.spec.name: tool for tool in tools}

    def specs(self) -> list[ToolSpec]:
        return [tool.spec for tool in self._tools.values()]

    def openai_tools(self) -> list[dict[str, Any]]:
        return [spec.to_openai_tool() for spec in self.specs()]

    def execute(self, context: ToolSessionContext, invocation: ToolInvocation) -> ToolResult:
        tool = self._tools.get(invocation.name)
        if tool is None:
            return ToolResult(invocation.name, "error", f"Unknown tool '{invocation.name}'")
        try:
            return tool.execute(context, invocation)
        except Exception as exc:
            return ToolResult(invocation.name, "error", str(exc))


def create_with_runtime_catalog() -> ToolCatalog:
    return ToolCatalog(
        [
            PrintProjectTreeTool(),
            OpenFileTool(),
            SearchSymbolTool(),
            GetTestErrorTool(),
            GetExecutionTraceTool(),
            GetFramesTool(),
            GetVariableChangeTool(),
            ApplyPatchTool(),
        ]
    )


def create_without_runtime_catalog() -> ToolCatalog:
    return ToolCatalog(
        [
            PrintProjectTreeTool(),
            OpenFileTool(),
            SearchSymbolTool(),
            ApplyPatchTool(),
        ]
    )


def parse_tool_invocation_from_call(tool_call: Any) -> ToolInvocation:
    fn = getattr(tool_call, "function", None)
    if fn is None:
        raise ValueError("Missing function payload")

    name = str(getattr(fn, "name", "")).strip()
    if not name:
        raise ValueError("Missing function name")

    raw_args = getattr(fn, "arguments", "{}") or "{}"
    payload = json.loads(raw_args)
    if not isinstance(payload, Mapping):
        raise ValueError("Function arguments must be an object")

    tool_call_id = str(getattr(tool_call, "id", "")).strip() or None
    return ToolInvocation(name=name, arguments=dict(payload), tool_call_id=tool_call_id)
