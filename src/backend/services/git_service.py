import json
import os
import subprocess
from pathlib import Path

from json_repair import repair_json

from config import settings


def _repo_dir(project_id: int) -> str:
    return os.path.join(settings.REPOS_DIR, str(project_id))


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


def ensure_repo(project_id: int, git_repo_url: str) -> str:
    repo_dir = _repo_dir(project_id)
    if os.path.exists(repo_dir):
        pull_repo(project_id)
    else:
        clone_repo(project_id, git_repo_url)
    return repo_dir


def read_file(project_id: int, relative_path: str) -> str | None:
    repo_dir = _repo_dir(project_id)
    file_path = os.path.join(repo_dir, relative_path)
    if not os.path.isfile(file_path):
        return None
    return Path(file_path).read_text(encoding="utf-8")


def read_json(project_id: int, relative_path: str) -> dict | None:
    content = read_file(project_id, relative_path)
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


def file_exists(project_id: int, relative_path: str) -> bool:
    repo_dir = _repo_dir(project_id)
    return os.path.isfile(os.path.join(repo_dir, relative_path))
