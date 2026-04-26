from __future__ import annotations

import sysconfig
from typing import Protocol, Sequence, Tuple, runtime_checkable

from libs.frames.frame import Frame


@runtime_checkable
class FrameFilter(Protocol):
    def keep(self, frame: Frame) -> bool: ...


class FrozenOrSyntheticFrameFilter:
    SKIP_SUBSTRINGS: Tuple[str, ...] = ("<", "frozen")

    def keep(self, frame: Frame) -> bool:
        return not any(s in frame.file for s in self.SKIP_SUBSTRINGS)


class SitePackagesFrameFilter:
    MARKER = "site-packages"

    def keep(self, frame: Frame) -> bool:
        return self.MARKER not in frame.file


class StdlibFrameFilter:
    def __init__(self, stdlib_paths: Sequence[str] | None = None):
        if stdlib_paths is None:
            stdlib_paths = self._default_stdlib_paths()
        self._stdlib_paths = tuple(p for p in stdlib_paths if p)

    @staticmethod
    def _default_stdlib_paths() -> Tuple[str, ...]:
        paths = []
        for key in ("stdlib", "platstdlib"):
            p = sysconfig.get_path(key)
            if p:
                paths.append(p)
        return tuple(paths)

    def keep(self, frame: Frame) -> bool:
        path = frame.file
        if not isinstance(path, str):
            return False
        if not path.endswith(".py"):
            return False
        if "/lib/python" in path:
            return False
        if path.endswith("/conftest.py"):
            return False
        if any(path.startswith(p) for p in self._stdlib_paths):
            return False
        return True


class TestbedOnlyFrameFilter:
    def __init__(self, marker: str = "/testbed/"):
        self._marker = marker

    def keep(self, frame: Frame) -> bool:
        return self._marker in frame.file and "site-packages" not in frame.file


class DedupFrameFilter:
    def __init__(self, by: Tuple[str, ...] = ("file", "func")):
        if not by:
            raise ValueError("DedupFrameFilter requires at least one attribute")
        self._by = by
        self._seen: set[tuple] = set()

    def keep(self, frame: Frame) -> bool:
        key = tuple(getattr(frame, attr) for attr in self._by)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True


class MaxEntriesFrameFilter:
    def __init__(self, n: int):
        if n < 0:
            raise ValueError("n must be >= 0")
        self._max = n
        self._count = 0

    def keep(self, frame: Frame) -> bool:
        if self._count >= self._max:
            return False
        self._count += 1
        return True
