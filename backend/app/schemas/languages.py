"""Supported source languages shared by validation and responses."""

from __future__ import annotations

SUPPORTED_LANGUAGES: dict[str, str] = {
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "python": "Python",
    "java": "Java",
    "csharp": "C#",
    "cpp": "C++",
    "go": "Go",
    "rust": "Rust",
    "php": "PHP",
}


def language_label(language: str) -> str:
    return SUPPORTED_LANGUAGES.get(language, language)


def supported_language_list() -> str:
    return ", ".join(sorted(SUPPORTED_LANGUAGES))
