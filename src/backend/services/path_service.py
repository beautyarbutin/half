import os
import re


_JSON_PATH_PATTERN = re.compile(r"([A-Za-z0-9._\-/]+\.json)\b")


def safe_join(base: str, relative: str) -> str:
    """Safely join base and relative paths, preventing directory traversal.

    Raises PermissionError if the resulting path escapes the base directory.
    """
    joined = os.path.realpath(os.path.join(base, relative))
    base_real = os.path.realpath(base)
    if not (joined == base_real or joined.startswith(base_real + os.sep)):
        raise PermissionError(f"Path traversal detected: '{relative}' escapes base directory")
    return joined


def _sanitize_path(path: str) -> str:
    """Remove directory traversal components from a relative path."""
    # Normalize path separators and remove any .. components
    parts = path.replace("\\", "/").split("/")
    sanitized = [p for p in parts if p and p != ".."]
    return "/".join(sanitized).lstrip("/")


def extract_json_path(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""

    match = _JSON_PATH_PATTERN.search(text)
    if match:
        return _sanitize_path(match.group(1))

    first_segment = re.split(r"[\s,，;；]+", text, maxsplit=1)[0].strip()
    return _sanitize_path(first_segment)


def normalize_expected_output_path(raw_value: str | None, default_path: str, collaboration_dir: str = "") -> str:
    candidate = extract_json_path(raw_value) or _sanitize_path(default_path)
    collab = (collaboration_dir or "").strip("/")
    if collab.startswith("outputs/") and candidate.startswith("outputs/") and not candidate.startswith(collab + "/"):
        candidate = candidate[len("outputs/"):]
    if collab and candidate != collab and not candidate.startswith(collab + "/"):
        return f"{collab}/{candidate}"
    return candidate
