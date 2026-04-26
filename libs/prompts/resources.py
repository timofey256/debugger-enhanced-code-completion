from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT_MARKERS = ("flake.nix", "pyproject.toml", ".git")


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if any((candidate / marker).exists() for marker in _REPO_ROOT_MARKERS):
            return candidate
    raise RuntimeError(
        f"Could not locate repository root from {start} (looked for: {_REPO_ROOT_MARKERS})"
    )


def _resources_root() -> Path:
    override = os.environ.get("PROMPT_RESOURCES_DIR")
    if override:
        return Path(override)
    return _find_repo_root(Path(__file__).resolve()) / "data" / "prompts"


def load_prompt(relative_path: str) -> str:
    path = _resources_root() / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"Prompt resource not found: {path}")
    return path.read_text(encoding="utf-8")
