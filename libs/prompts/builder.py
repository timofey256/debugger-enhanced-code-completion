from __future__ import annotations

from typing import List, Tuple


class PromptBuilder:
    def __init__(self) -> None:
        self._sections: List[Tuple[str, str]] = []

    def add_section(self, section_name: str, section_body: str) -> "PromptBuilder":
        self._sections.append((section_name, section_body))
        return self

    def build(self) -> str:
        if not self._sections:
            return ""
        return "\n\n".join(f"<{name}>\n{body}" for name, body in self._sections)
