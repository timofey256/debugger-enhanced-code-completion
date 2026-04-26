from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


def _freeze_mapping(m: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(m))


@dataclass(frozen=True)
class Frame:
    file: str
    line: int
    func: str
    locals: Mapping[str, Any] = field(default_factory=dict)
    meta: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> "Frame":
        return cls(
            file=str(d["file"]),
            line=int(d["line"]),
            func=str(d["func"]),
            locals=_freeze_mapping(d.get("locals", {})),
            meta=_freeze_mapping(d.get("meta", {})),
        )

    def to_json(self) -> dict:
        out: dict = {
            "file": self.file,
            "line": self.line,
            "func": self.func,
            "locals": dict(self.locals),
        }
        if self.meta:
            out["meta"] = dict(self.meta)
        return out

    def with_locals(self, new_locals: Mapping[str, Any]) -> "Frame":
        return Frame(
            file=self.file,
            line=self.line,
            func=self.func,
            locals=_freeze_mapping(new_locals),
            meta=self.meta,
        )
