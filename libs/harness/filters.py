from __future__ import annotations

from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class PathFilter(Protocol):
    def keep(self, path: str) -> bool: ...


class StdlibFilter:
    def keep(self, path: str) -> bool:
        if not isinstance(path, str):
            return False
        if not path.endswith(".py"):
            return False
        if "site-packages" in path:
            return False
        if "/lib/python" in path:
            return False
        if path.endswith("/conftest.py"):
            return False
        return True

    def keep_frame(self, frame: Dict[str, Any]) -> bool:
        if not isinstance(frame, dict):
            return False
        file_path = frame.get("file")
        line = frame.get("line")
        if not isinstance(file_path, str) or not isinstance(line, int):
            return False
        return self.keep(file_path)
