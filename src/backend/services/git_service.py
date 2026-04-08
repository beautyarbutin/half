import json
import os
import subprocess
import configparser
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

# Per-project TTL for ensure_repo. Successive calls within this window reuse the
# previous fetch/pull instead of hitting the remote again. Keeps "frontend
# pre-checks then immediately dispatches" from doing two back-to-back git fetches.
_ENSURE_REPO_TTL_SECONDS = 3.0
_ensure_repo_last_run: dict[int, float] = {}

import logging

from json_repair import repair_json

from config import settings

logger = logging.getLogger("half.git")


_FORBIDDEN_GIT_PREFIXES = ("file://", "ext::", "-")
_FORBIDDEN_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "169.254.169.254"}
_PRIVATE_HOST_PREFIXES = ("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.",
                          "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
                          "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.")


def validate_git_url(url: str) -> str:
    """Validate a git remote URL against SSRF / dangerous-protocol abuse.

    Allows: ``git@host:path``, ``ssh://git@host/path``, ``https://host/path``.
    Rejects: ``file://``, ``ext::``, leading-dash injection, private/loopback
    hosts, and link-local metadata services.
    """
    if not url or not isinstance(url, str):
        raise ValueError("git_repo_url is required")
    value = url.strip()
    lowered = value.lower()
    for bad in _FORBIDDEN_GIT_PREFIXES:
        if lowered.startswith(bad):
            raise ValueError(f"git_repo_url uses forbidden protocol/prefix: {bad}")

    host: str | None = None
    if value.startswith("git@") and ":" in value:
        host = value.split("@", 1)[1].split(":", 1)[0].lower()
    else:
        parsed = urlparse(value)
        if parsed.scheme not in ("https", "ssh"):
            raise ValueError("git_repo_url must use https, ssh, or git@host:path form")
        host = (parsed.hostname or "").lower()

    if not host:
        raise ValueError("git_repo_url is missing a host")
    if host in _FORBIDDEN_HOSTS or host.startswith(_PRIVATE_HOST_PREFIXES):
        raise ValueError(f"git_repo_url host is not allowed: {host}")
    return value


def _repo_dir(project_id: int) -> str:
    return os.path.join(settings.REPOS_DIR, str(project_id))


def _safe_join(base: str, relative_path: str) -> str:
    """Join a relative path to base and reject any traversal outside base."""
    base_real = os.path.realpath(base)
    candidate = os.path.realpath(os.path.join(base_real, _normalize_relative(relative_path)))
    if candidate != base_real and not candidate.startswith(base_real + os.sep):
        raise PermissionError(f"path escapes repo root: {relative_path}")
    return candidate


def clone_repo(project_id: int, git_repo_url: str) -> str:
    repo_dir = _repo_dir(project_id)
    if os.path.exists(repo_dir):
        return repo_dir
    os.makedirs(settings.REPOS_DIR, exist_ok=True)
    subprocess.run(
        ["git", "clone", git_repo_url, repo_dir],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return repo_dir


def pull_repo(project_id: int) -> str:
    repo_dir = _repo_dir(project_id)
    if not os.path.exists(repo_dir):
        raise FileNotFoundError(f"Repo directory not found: {repo_dir}")
    subprocess.run(
        ["git", "-C", repo_dir, "pull", "--ff-only"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return repo_dir


def fetch_repo(project_id: int) -> str:
    repo_dir = _repo_dir(project_id)
    if not os.path.exists(repo_dir):
        raise FileNotFoundError(f"Repo directory not found: {repo_dir}")
    subprocess.run(
        ["git", "-C", repo_dir, "fetch", "origin"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return repo_dir


def ensure_repo(project_id: int, git_repo_url: str) -> str:
    repo_dir = _repo_dir(project_id)
    now = time.monotonic()
    last = _ensure_repo_last_run.get(project_id)
    if last is not None and (now - last) < _ENSURE_REPO_TTL_SECONDS and os.path.exists(repo_dir):
        return repo_dir
    if os.path.exists(repo_dir):
        try:
            fetch_repo(project_id)
        except Exception as e:
            logger.warning("git fetch failed for project %s: %s", project_id, e)
        try:
            pull_repo(project_id)
        except Exception as e:
            logger.warning("git pull failed for project %s: %s", project_id, e)
    else:
        clone_repo(project_id, git_repo_url)
    _ensure_repo_last_run[project_id] = time.monotonic()
    return repo_dir


def _normalize_relative(relative_path: str) -> str:
    """Strip any leading slashes so os.path.join treats the path as relative.

    Without this, a path like "/v2/plan.json" would be interpreted as an
    absolute filesystem path by os.path.join, completely discarding the
    repo_dir prefix.
    """
    return (relative_path or "").lstrip("/")


def _normalize_repo_identity(repo_url: str | None) -> str | None:
    if not repo_url:
        return None

    value = repo_url.strip()
    if not value:
        return None

    # SSH format: git@github.com:org/repo.git -> github.com/org/repo
    if value.startswith("git@") and ":" in value:
        # Split at the first colon to get user@host and path parts
        user_host_part, path_part = value.split(":", 1)
        # Extract host from "git@github.com" by splitting at @
        if "@" in user_host_part:
            host = user_host_part.split("@", 1)[1].lower()
        else:
            host = user_host_part.lower()
        path = path_part
        if path.endswith(".git"):
            path = path[:-4]
        return f"{host}/{path.strip('/')}"

    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        path = parsed.path[:-4] if parsed.path.endswith(".git") else parsed.path
        return f"{parsed.netloc.lower()}/{path.strip('/')}"

    normalized = value[:-4] if value.endswith(".git") else value
    return normalized.strip("/") or None


@lru_cache(maxsize=1)
def _workspace_repo_identity() -> str | None:
    workspace_root = settings.WORKSPACE_ROOT
    if not workspace_root or not os.path.isdir(workspace_root):
        return None

    git_config_path = os.path.join(workspace_root, ".git", "config")
    if os.path.isfile(git_config_path):
        parser = configparser.ConfigParser()
        try:
            parser.read(git_config_path, encoding="utf-8")
            remote_url = parser.get('remote "origin"', "url", fallback=None)
        except Exception:
            remote_url = None
        normalized = _normalize_repo_identity(remote_url)
        if normalized:
            return normalized

    try:
        result = subprocess.run(
            ["git", "-C", workspace_root, "remote", "get-url", "origin"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None

    return _normalize_repo_identity(result.stdout)


def _workspace_path(relative_path: str, git_repo_url: str | None) -> str | None:
    workspace_root = settings.WORKSPACE_ROOT
    if not workspace_root or not os.path.isdir(workspace_root):
        return None

    if _workspace_repo_identity() != _normalize_repo_identity(git_repo_url):
        return None

    return os.path.join(workspace_root, _normalize_relative(relative_path))


def _remote_head_ref(project_id: int) -> str | None:
    repo_dir = _repo_dir(project_id)
    if not os.path.isdir(repo_dir):
        return None

    try:
        result = subprocess.run(
            ["git", "-C", repo_dir, "symbolic-ref", "refs/remotes/origin/HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return "refs/remotes/origin/main"

    ref = result.stdout.strip()
    return ref or "refs/remotes/origin/main"


def _read_remote_file(project_id: int, relative_path: str) -> str | None:
    repo_dir = _repo_dir(project_id)
    if not os.path.isdir(repo_dir):
        return None

    ref = _remote_head_ref(project_id)
    if not ref:
        return None

    object_spec = f"{ref}:{_normalize_relative(relative_path)}"
    try:
        result = subprocess.run(
            ["git", "-C", repo_dir, "show", object_spec],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        return None

    return result.stdout


def read_file(project_id: int, relative_path: str, git_repo_url: str | None = None) -> str | None:
    repo_dir = _repo_dir(project_id)
    try:
        file_path = _safe_join(repo_dir, relative_path)
    except PermissionError:
        return None
    if os.path.isfile(file_path):
        return Path(file_path).read_text(encoding="utf-8")

    workspace_file_path = _workspace_path(relative_path, git_repo_url)
    if workspace_file_path and os.path.isfile(workspace_file_path):
        return Path(workspace_file_path).read_text(encoding="utf-8")

    return _read_remote_file(project_id, relative_path)


def read_json(project_id: int, relative_path: str, git_repo_url: str | None = None) -> dict | None:
    content = read_file(project_id, relative_path, git_repo_url=git_repo_url)
    if content is None:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        try:
            repaired = repair_json(content)
            return json.loads(repaired)
        except Exception:
            return None


def list_dir(project_id: int, relative_path: str, git_repo_url: str | None = None) -> list[str]:
    """List immediate entries in a repo subdirectory. Returns [] if not a dir."""
    repo_dir = _repo_dir(project_id)
    try:
        candidate = _safe_join(repo_dir, relative_path)
    except PermissionError:
        return []
    if os.path.isdir(candidate):
        try:
            return sorted(os.listdir(candidate))
        except OSError:
            return []

    workspace_dir = _workspace_path(relative_path, git_repo_url)
    if workspace_dir and os.path.isdir(workspace_dir):
        try:
            return sorted(os.listdir(workspace_dir))
        except OSError:
            return []
    return []


def dir_has_content(project_id: int, relative_path: str, git_repo_url: str | None = None) -> bool:
    """True if relative_path is a directory containing at least one non-empty file."""
    repo_dir = _repo_dir(project_id)
    candidates: list[str] = []
    try:
        candidates.append(_safe_join(repo_dir, relative_path))
    except PermissionError:
        pass
    workspace_dir = _workspace_path(relative_path, git_repo_url)
    if workspace_dir:
        candidates.append(workspace_dir)
    for path in candidates:
        if not os.path.isdir(path):
            continue
        for root, _dirs, files in os.walk(path):
            for name in files:
                full = os.path.join(root, name)
                try:
                    if os.path.getsize(full) > 0:
                        return True
                except OSError:
                    continue
    return False


def file_exists(project_id: int, relative_path: str, git_repo_url: str | None = None) -> bool:
    repo_dir = _repo_dir(project_id)
    try:
        candidate = _safe_join(repo_dir, relative_path)
    except PermissionError:
        return False
    if os.path.isfile(candidate):
        return True

    workspace_file_path = _workspace_path(relative_path, git_repo_url)
    if workspace_file_path and os.path.isfile(workspace_file_path):
        return True

    return _read_remote_file(project_id, relative_path) is not None
