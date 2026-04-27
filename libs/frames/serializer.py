from __future__ import annotations

import json
import textwrap
from typing import Any, Iterable, Mapping, Optional

from libs.frames.frame import Frame

try:
    import jsonpickle as _jsonpickle
    _HAS_JSONPICKLE = True
except ImportError:
    _jsonpickle = None
    _HAS_JSONPICKLE = False


class LocalsSerializer:
    DEFAULT_CUTOFF = 1000
    UNSERIALIZABLE = "<unserializable>"

    def __init__(self, cutoff: int = DEFAULT_CUTOFF, prefer_jsonpickle: bool = True):
        if cutoff < 0:
            raise ValueError("cutoff must be >= 0")
        self._cutoff = cutoff
        self._use_jsonpickle = prefer_jsonpickle and _HAS_JSONPICKLE

    @property
    def cutoff(self) -> int:
        return self._cutoff

    def serialize(self, locals_mapping: Mapping[str, Any]) -> dict[str, str]:
        out: dict[str, str] = {}
        for key, value in locals_mapping.items():
            out[str(key)] = self._serialize_value(value)
        return out

    def _serialize_value(self, value: Any) -> str:
        try:
            if self._use_jsonpickle:
                serialized = str(_jsonpickle.dumps(value, unpicklable=False))
            else:
                serialized = repr(value)
        except Exception:
            return self.UNSERIALIZABLE
        return serialized[: self._cutoff]


class FrameSerializer:
    def __init__(
        self,
        source_map: Mapping[str, str],
        context_size: int,
        locals_serializer: Optional[LocalsSerializer] = None,
    ):
        self._source_map = source_map
        self._context_size = context_size
        self._locals_serializer = locals_serializer

    def to_string(self, frame: Frame, index: int = 0) -> str:
        from libs.harness.io_utils import render_source_context

        filename = frame.file
        function_name = frame.func
        line_number = frame.line if isinstance(frame.line, int) else 1
        source = self._source_map.get(filename, "")
        context = render_source_context(source, line_number, self._context_size)
        locals_text = self._render_locals(frame.locals)
        return textwrap.dedent(
            f"""\
            Block {index}:
            File: {filename}
            Function name: {function_name}
            Line: {line_number}
            Context:
            {context}
            Locals: {locals_text}
            """
        ).strip()

    def to_string_many(self, frames: Iterable[Frame]) -> str:
        return "\n\n".join(
            self.to_string(frame, index) for index, frame in enumerate(frames)
        )

    def _render_locals(self, locals_payload: Any) -> str:
        if self._locals_serializer is not None and isinstance(
            locals_payload, Mapping
        ):
            serialized = self._locals_serializer.serialize(locals_payload)
            return json.dumps(serialized, ensure_ascii=False, indent=2, default=str)
        if isinstance(locals_payload, Mapping):
            return json.dumps(
                dict(locals_payload), ensure_ascii=False, indent=2, default=str
            )
        if isinstance(locals_payload, list):
            return json.dumps(
                locals_payload, ensure_ascii=False, indent=2, default=str
            )
        return str(locals_payload)


class ExecutionPathSerializer:
    HEADER = "## Execution path (functions called during test)"

    def to_string(self, frames: Iterable[Frame]) -> str:
        lines = [
            f"  {frame.file}:{frame.line} in {frame.func}()" for frame in frames
        ]
        if not lines:
            return ""
        return self.HEADER + "\n" + "\n".join(lines)
