"""Shared helpers for converting live Python frames into raw JSON-serializable dicts.

In-process tracers use these helpers to capture frames without path-based
filtering; host-side filtering still happens later via
libs.frames.FramesFilteringPipeline. Per-value size and per-frame locals counts
ARE bounded here, because unbounded capture of large objects (e.g. Django
querysets) on every traced line exhausts container memory and produces
multi-gigabyte trace files.

This module must stay importable on the oldest interpreter any testbed pins
(Python 3.6), so it avoids `from __future__ import annotations` and any
3.7+-only syntax.
"""

try:
    import jsonpickle as _jsonpickle
    _HAS_JSONPICKLE = True
except ImportError:
    _jsonpickle = None
    _HAS_JSONPICKLE = False


_UNSERIALIZABLE = "<unserializable>"
_MAX_VALUE_CHARS = 400
_MAX_LOCALS = 30


def serialize_value_raw(value) -> str:
    try:
        if _HAS_JSONPICKLE:
            out = str(_jsonpickle.dumps(value, unpicklable=False))
        else:
            out = repr(value)
    except Exception:
        return _UNSERIALIZABLE
    if len(out) > _MAX_VALUE_CHARS:
        return out[:_MAX_VALUE_CHARS] + "...<truncated>"
    return out


def serialize_locals_raw(locals_mapping) -> dict:
    out = {}
    for index, (k, v) in enumerate(locals_mapping.items()):
        if index >= _MAX_LOCALS:
            out["<truncated>"] = "%d more locals" % (len(locals_mapping) - _MAX_LOCALS)
            break
        out[str(k)] = serialize_value_raw(v)
    return out


def frame_to_raw_dict(py_frame, line: int) -> dict:
    return {
        "file": py_frame.f_code.co_filename,
        "line": line,
        "func": py_frame.f_code.co_name,
        "locals": serialize_locals_raw(py_frame.f_locals),
    }
