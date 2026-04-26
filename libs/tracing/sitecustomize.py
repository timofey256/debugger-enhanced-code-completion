"""
Auto-activation of trace collectors via PYTHONPATH.

This file is automatically executed when Python starts if it's in PYTHONPATH.
It detects the testing framework and injects the appropriate tracer.
"""

import os
import sys


def should_activate() -> bool:
    """Check if we should activate tracing.

    We activate if AUTO_DEBUG_JSON is set, indicating trace collection is enabled.
    """
    # Simply check if AUTO_DEBUG_JSON environment variable is set
    # This is a clear signal that trace collection should be active
    auto_debug_json = os.environ.get('AUTO_DEBUG_JSON')

    if auto_debug_json:
        # Only activate for actual test runs, not for conda/pip invocations
        # Check sys.argv if available to filter out conda/pip
        if hasattr(sys, 'argv') and sys.argv:
            argv_str = " ".join(sys.argv)
            # Skip activation for conda and pip
            if 'conda' in argv_str or 'pip' in argv_str or 'setup.py' in argv_str:
                return False

        # AUTO_DEBUG_JSON is set and we're not in conda/pip, so activate
        return True

    return False


def detect_framework() -> str:
    """Detect which testing framework is being used.

    Honors the AUTO_DEBUG_FRAMEWORK env var when set by FrameworkDetector
    on the host. Falls back to argv/sys.modules sniffing only if absent.
    """
    declared = os.environ.get('AUTO_DEBUG_FRAMEWORK')
    if declared in ('pytest', 'unittest', 'django', 'unknown'):
        return declared

    argv_str = ""
    if hasattr(sys, 'argv') and sys.argv:
        argv_str = " ".join(sys.argv)

    if argv_str and ("pytest" in argv_str or "py.test" in argv_str):
        return "pytest"

    if argv_str and ("unittest" in argv_str or "python -m unittest" in argv_str):
        return "unittest"

    if argv_str and ("manage.py test" in argv_str or "runtests.py" in argv_str):
        return "django"

    if "django" in sys.modules:
        return "django"

    if "pytest" in sys.modules:
        return "pytest"

    if "unittest" in sys.modules:
        return "unittest"

    return "unknown"


def inject_tracer():
    """Inject appropriate tracer based on detected framework."""
    # Check if we should activate
    if not should_activate():
        return

    # Debug: Log activation
    debug_enabled = os.environ.get('AUTO_DEBUG_JSON')
    if debug_enabled:
        argv_info = f"sys.argv={sys.argv}" if hasattr(sys, 'argv') else "no sys.argv"
        print(f"DEBUG sitecustomize: ACTIVATING trace collection ({argv_info})", file=sys.stderr)

    framework = detect_framework()
    if debug_enabled:
        print(f"DEBUG sitecustomize: Detected framework: {framework}", file=sys.stderr)

    try:
        # For all cases, we want to inject the tracer
        # We'll handle Django specially but also patch unittest as a fallback
        
        if framework == "pytest":
            # For pytest, we need to ensure conftest.py is in place
            # This is handled by copying the file to the test directory
            pass  # pytest uses conftest.py, not runtime injection

        elif framework == "django" or framework == "unknown":
            # For Django or unknown, try Django tracer first, then fall back to unittest
            # This handles the case where runtests.py doesn't show up in sys.argv
            from django_tracer_new import inject_django_tracer
            inject_django_tracer()

        else:
            # For unittest - inject unittest tracer
            from unittest_tracer import inject_unittest_tracer
            inject_unittest_tracer()

    except Exception as e:
        # Don't silently fail during development - print errors
        import traceback
        print(f"ERROR in sitecustomize: Failed to inject tracer: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)


# Auto-activate when this module is imported
inject_tracer()
