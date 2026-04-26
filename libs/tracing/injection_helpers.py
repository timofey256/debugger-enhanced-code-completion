"""
Helper utilities for injecting trace collectors into test environments.
"""

import os
import shutil
from pathlib import Path
from typing import Optional


def copy_pytest_conftest(target_dir: str, conftest_source: str) -> bool:
    """
    Copy pytest conftest.py to target directory.

    Args:
        target_dir: Directory to copy conftest.py to
        conftest_source: Path to source conftest.py template

    Returns:
        True if successful, False otherwise
    """
    try:
        target_path = Path(target_dir) / "conftest.py"
        source_path = Path(conftest_source)

        if not source_path.exists():
            print(f"Error: Source conftest not found: {source_path}")
            return False

        # Check if conftest already exists
        if target_path.exists():
            # Backup existing conftest
            backup_path = target_path.with_suffix(".py.backup")
            shutil.copy(target_path, backup_path)
            print(f"Backed up existing conftest to {backup_path}")

        # Copy our conftest
        shutil.copy(source_path, target_path)
        print(f"Copied conftest.py to {target_path}")

        return True

    except Exception as e:
        print(f"Error copying conftest: {e}")
        return False


def setup_pythonpath(tracers_dir: str) -> str:
    """
    Generate PYTHONPATH value that includes trace collectors.

    Args:
        tracers_dir: Path to libs/tracing directory

    Returns:
        PYTHONPATH string to use in Docker environment
    """
    current_pythonpath = os.environ.get("PYTHONPATH", "")

    if current_pythonpath:
        return f"{tracers_dir}:{current_pythonpath}"
    else:
        return tracers_dir


def install_dependencies(pip_command: str = "pip") -> bool:
    """
    Install required dependencies for trace collection.

    Args:
        pip_command: pip command to use

    Returns:
        True if successful, False otherwise
    """
    try:
        import subprocess

        dependencies = ["jsonpickle"]

        result = subprocess.run(
            [pip_command, "install", *dependencies],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode == 0:
            print("Successfully installed trace collector dependencies")
            return True
        else:
            print(f"Failed to install dependencies: {result.stderr}")
            return False

    except Exception as e:
        print(f"Error installing dependencies: {e}")
        return False
