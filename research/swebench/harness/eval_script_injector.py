"""
Eval script injection for trace collection setup.

This module modifies SWE-bench eval scripts to inject trace collection setup,
particularly for pytest which requires conftest.py in the test directory.
"""

import sys
from dataclasses import replace
from typing import List

from libs.env import require_env

sys.path.insert(0, require_env("SWE_BENCH_PATH"))
from swebench.harness.test_spec.test_spec import TestSpec


def should_inject_conftest(test_spec: TestSpec) -> bool:
    """
    Determine if we should inject conftest.py for pytest.

    Args:
        test_spec: SWE-bench TestSpec

    Returns:
        True if test uses pytest and needs conftest injection
    """
    # Check eval_script_list for pytest commands
    eval_script = " ".join(test_spec.eval_script_list).lower()

    # Pytest indicators
    pytest_indicators = ["pytest", "py.test"]

    return any(indicator in eval_script for indicator in pytest_indicators)


def should_activate_unittest(test_spec: TestSpec) -> bool:
    """
    Determine if test uses unittest (sitecustomize.py handles this).

    Args:
        test_spec: SWE-bench TestSpec

    Returns:
        True if test uses unittest/django
    """
    eval_script = " ".join(test_spec.eval_script_list).lower()

    # Unittest/Django indicators
    unittest_indicators = ["unittest", "manage.py test", "python -m unittest", "runtests.py"]

    return any(indicator in eval_script for indicator in unittest_indicators)


def inject_pytest_conftest(test_spec: TestSpec) -> TestSpec:
    """
    Inject pytest conftest.py setup into eval script.

    Adds commands to:
    1. Export environment variables for trace collection
    2. Backup existing conftest.py if present
    3. Copy pytest_tracer.py as conftest.py
    4. Ensure /trace_output is writable

    Args:
        test_spec: Original TestSpec

    Returns:
        Modified TestSpec with conftest injection commands
    """
    # Commands to inject BEFORE test execution
    injection_commands = [
        # Export environment variables for trace collection
        "export PYTHONPATH=/opt/tracers:/testbed:$PYTHONPATH",
        "export AUTO_DEBUG_JSON=/trace_output/auto_debug.json",

        # Ensure trace output directory is writable
        "chmod 777 /trace_output || true",

        # Install jsonpickle for locals serialization
        "pip install jsonpickle -q || true",

        # Backup existing conftest.py if present in testbed root
        "if [ -f /testbed/conftest.py ]; then",
        "    echo 'Backing up existing /testbed/conftest.py'",
        "    cp /testbed/conftest.py /testbed/conftest.py.bak",
        "fi",

        # Copy our pytest tracer as conftest.py
        "echo 'Installing trace collector conftest.py'",
        "cp /opt/tracers/pytest_tracer.py /testbed/conftest.py",
        "chmod 644 /testbed/conftest.py",

        # Verify it was copied
        "if [ ! -f /testbed/conftest.py ]; then",
        "    echo 'ERROR: Failed to install conftest.py'",
        "    exit 1",
        "fi",

        "echo 'Trace collection setup complete'",
    ]

    # Create new eval_script_list with injection at the beginning
    new_eval_script_list = injection_commands + test_spec.eval_script_list

    # Return modified TestSpec (using dataclass replace)
    return replace(test_spec, eval_script_list=new_eval_script_list)


def inject_unittest_setup(test_spec: TestSpec) -> TestSpec:
    """
    Inject unittest trace setup into eval script.

    For unittest, sitecustomize.py auto-activates via PYTHONPATH,
    but we need to export environment variables and ensure /trace_output is writable.

    Args:
        test_spec: Original TestSpec

    Returns:
        Modified TestSpec with minimal setup commands
    """
    # Minimal setup for unittest (sitecustomize.py handles the rest)
    injection_commands = [
        # Export environment variables for trace collection
        "export PYTHONPATH=/opt/tracers:/testbed:$PYTHONPATH",
        "export AUTO_DEBUG_JSON=/trace_output/auto_debug.json",

        # Ensure trace output directory is writable
        "chmod 777 /trace_output || true",

        # Install jsonpickle for locals serialization
        "pip install jsonpickle -q || true",

        "echo 'Trace collection setup complete (unittest via sitecustomize.py)'",
    ]

    # Create new eval_script_list with injection at the beginning
    new_eval_script_list = injection_commands + test_spec.eval_script_list

    # Return modified TestSpec
    return replace(test_spec, eval_script_list=new_eval_script_list)


def inject_trace_setup(test_spec: TestSpec) -> TestSpec:
    """
    Inject appropriate trace collection setup based on framework.

    This is the main entry point that detects the framework and
    injects the appropriate setup.

    Args:
        test_spec: Original TestSpec

    Returns:
        Modified TestSpec with trace collection setup
    """
    if should_inject_conftest(test_spec):
        # pytest - needs conftest.py injection
        return inject_pytest_conftest(test_spec)
    elif should_activate_unittest(test_spec):
        # unittest/Django - minimal setup, sitecustomize.py handles it
        return inject_unittest_setup(test_spec)
    else:
        # Unknown framework or custom test runner
        # Add minimal setup and hope sitecustomize.py works
        return inject_unittest_setup(test_spec)


def get_detected_framework(test_spec: TestSpec) -> str:
    """
    Get the detected framework for logging/debugging.

    Args:
        test_spec: TestSpec to analyze

    Returns:
        Framework name: "pytest", "unittest", or "unknown"
    """
    if should_inject_conftest(test_spec):
        return "pytest"
    elif should_activate_unittest(test_spec):
        return "unittest"
    else:
        return "unknown"
