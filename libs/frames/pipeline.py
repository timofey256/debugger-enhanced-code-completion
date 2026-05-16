from __future__ import annotations

from typing import Iterable, Sequence

from libs.frames.frame import Frame
from libs.frames.filters import (
    FrameFilter,
    FrozenOrSyntheticFrameFilter,
    SitePackagesFrameFilter,
    StdlibFrameFilter,
    TestbedOnlyFrameFilter,
    ConftestFrameFilter,
    DedupFrameFilter,
    MaxEntriesFrameFilter,
)
from libs.frames.serializer import LocalsSerializer


class FramesFilteringPipeline:
    def __init__(
        self,
        filters: Sequence[FrameFilter],
        serializer: LocalsSerializer,
    ):
        self._filters = list(filters)
        self._serializer = serializer

    @property
    def filters(self) -> Sequence[FrameFilter]:
        return tuple(self._filters)

    @property
    def serializer(self) -> LocalsSerializer:
        return self._serializer

    def run(self, frames: Iterable[Frame]) -> list[Frame]:
        out: list[Frame] = []
        for frame in frames:
            if all(f.keep(frame) for f in self._filters):
                serialized = self._serializer.serialize(frame.locals)
                out.append(frame.with_locals(serialized))
        return out


def default_traceback_pipeline() -> FramesFilteringPipeline:
    return FramesFilteringPipeline(
        filters=[
            FrozenOrSyntheticFrameFilter(),
            SitePackagesFrameFilter(),
            StdlibFrameFilter(),
            ConftestFrameFilter(),
        ],
        serializer=LocalsSerializer(cutoff=LocalsSerializer.DEFAULT_CUTOFF),
    )


def default_exec_path_pipeline() -> FramesFilteringPipeline:
    return FramesFilteringPipeline(
        filters=[
            TestbedOnlyFrameFilter(),
            ConftestFrameFilter(),
            DedupFrameFilter(by=("file", "func")),
            MaxEntriesFrameFilter(n=500),
        ],
        serializer=LocalsSerializer(cutoff=LocalsSerializer.DEFAULT_CUTOFF),
    )


def default_step_frames_pipeline() -> FramesFilteringPipeline:
    return FramesFilteringPipeline(
        filters=[
            TestbedOnlyFrameFilter(),
            ConftestFrameFilter(),
            DedupFrameFilter(by=("file", "func", "line")),
            MaxEntriesFrameFilter(n=2000),
        ],
        serializer=LocalsSerializer(cutoff=LocalsSerializer.DEFAULT_CUTOFF),
    )
