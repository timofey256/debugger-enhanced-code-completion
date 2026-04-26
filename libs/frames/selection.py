from __future__ import annotations

from typing import Any, Mapping, Sequence


def select_most_informative_trace(
    traces: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    if not traces:
        raise ValueError("Cannot select a trace from an empty sequence")
    return traces[0]
