"""Filesystem utilities for safe path generation, sanitization, and hierarchy creation."""

import re
from pathlib import Path
from typing import Union

# Regex matching characters that are invalid across Windows, Linux, and macOS file systems
ILLEGAL_CHARS_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(
    name: str,
    max_length: int = 200,
    replacement: str = "_",
    fallback: str = "sem_titulo",
) -> str:
    """Sanitizes a string to be safely used as a filename across all OS platforms.
    
    Args:
        name: Raw filename string (with or without extension).
        max_length: Maximum allowed length for the filename.
        replacement: Character to replace illegal characters with.
        fallback: Name used if the sanitized string ends up empty.
        
    Returns:
        Safe, sanitized filename string.
    """
    if not name:
        return fallback

    # Replace illegal characters
    sanitized = ILLEGAL_CHARS_PATTERN.sub(replacement, name)

    # Replace consecutive replacement chars and whitespace with single space/char
    sanitized = re.sub(rf"{re.escape(replacement)}+", replacement, sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()

    # Remove leading/trailing dots and spaces (problematic on Windows and hidden files)
    sanitized = sanitized.strip(". ")

    if not sanitized:
        sanitized = fallback

    # Length limit with preservation of extension if present
    if len(sanitized) > max_length:
        path = Path(sanitized)
        ext = path.suffix
        stem = path.stem
        allowed_stem_len = max_length - len(ext)
        if allowed_stem_len > 0:
            sanitized = f"{stem[:allowed_stem_len].rstrip('. ')}{ext}"
        else:
            sanitized = sanitized[:max_length].rstrip(". ")

    return sanitized or fallback


def sanitize_path_segment(
    name: str,
    max_length: int = 150,
    replacement: str = "_",
    fallback: str = "sem_nome",
) -> str:
    """Sanitizes a folder name segment (e.g. notebook, section group, section)."""
    return sanitize_filename(
        name=name,
        max_length=max_length,
        replacement=replacement,
        fallback=fallback,
    )


def ensure_directory(path: Union[str, Path]) -> Path:
    """Ensures that a directory exists, creating all parent directories if necessary."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_unique_path(target_path: Path) -> Path:
    """Generates an incremental unique path (e.g. file_1.png) if target already exists."""
    if not target_path.exists():
        return target_path

    parent = target_path.parent
    stem = target_path.stem
    suffix = target_path.suffix

    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
