"""Auto-activation of trace collectors via PYTHONPATH.

Loaded automatically when /opt/tracers is on PYTHONPATH. The host's
FrameworkDetector exports AUTO_DEBUG_JSON and AUTO_DEBUG_FRAMEWORK before
the tests run; this module reads those and injects the matching tracer.

Pytest is wired separately via a copied conftest.py and is intentionally
absent from the dispatch table.

Must stay importable on Python 3.6 testbeds, so no `from __future__ import
annotations` or other 3.7+-only syntax.
"""

import os
import sys
import traceback


_INJECTORS = {
    "django": ("django_tracer", "inject_django_tracer"),
    "unittest": ("unittest_tracer", "inject_unittest_tracer"),
    "sympy": ("sympy_tracer", "inject_sympy_tracer"),
    "unknown": ("unittest_tracer", "inject_unittest_tracer"),
}


def _inject() -> None:
    if not os.environ.get("AUTO_DEBUG_JSON"):
        return

    framework = os.environ.get("AUTO_DEBUG_FRAMEWORK", "unknown")
    target = _INJECTORS.get(framework)
    if target is None:
        return

    module_name, func_name = target
    try:
        module = __import__(module_name)
        getattr(module, func_name)()
    except Exception as exc:
        print(
            f"ERROR sitecustomize: failed to inject {func_name} "
            f"for framework={framework}: {exc}",
            file=sys.stderr,
        )
        traceback.print_exc(file=sys.stderr)


_inject()
