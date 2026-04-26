"""Shared helpers for converting live Python frames into raw JSON-serializable dicts.

In-process tracers use these helpers to capture every frame WITHOUT applying
path-based filtering or length truncation. Filtering and truncation happen
later, on the host, via libs.frames.FramesFilteringPipeline.
"""

from __future__ import annotations

try:
    import jsonpickle as _jsonpickle
    _HAS_JSONPICKLE = True
except ImportError:
    _jsonpickle = None
    _HAS_JSONPICKLE = False


_UNSERIALIZABLE = "<unserializable>"


def serialize_value_raw(value) -> str:
    try:
        if _HAS_JSONPICKLE:
            return str(_jsonpickle.dumps(value, unpicklable=False))
        return repr(value)
    except Exception:
        return _UNSERIALIZABLE


def serialize_locals_raw(locals_mapping) -> dict:
    out = {}
    for k, v in locals_mapping.items():
        out[str(k)] = serialize_value_raw(v)
    return out


def frame_to_raw_dict(py_frame, line: int) -> dict:
    return {
        "file": py_frame.f_code.co_filename,
        "line": line,
        "func": py_frame.f_code.co_name,
        "locals": serialize_locals_raw(py_frame.f_locals),
    }
