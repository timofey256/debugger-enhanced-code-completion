from __future__ import annotations

from typing import Any, Mapping

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
