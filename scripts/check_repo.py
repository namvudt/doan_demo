"""Reject local artifacts and recognizable credentials in the Git index."""

import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
LOCAL_DIRECTORIES = {
    ".api-demo",
    ".secrets",
    ".venv",
    "venv",
    "env",
    "ENV",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "reports",
    "logs",
    "data",
    "htmlcov",
}
LOCAL_FILES = {
    "postman/heritage-vqa.openapi.json",
    "docs/api-test-results.md",
    "docs/implementation-progress.md",
    "docs/observability-plan.md",
}
SECRET = re.compile(
    rb"(?:lsv2_[A-Za-z0-9_-]{24,}|AIza[A-Za-z0-9_-]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{32,})"
)


def main():
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    rejected = []
    checked = 0
    for name in filter(None, paths):
        parts = PurePosixPath(name).parts
        leaf = parts[-1]
        if (
            any(part in LOCAL_DIRECTORIES or part.startswith(".venv-") for part in parts[:-1])
            or leaf == ".env"
            or leaf.startswith(".env.")
            and leaf != ".env.example"
            or leaf.endswith((".sqlite", ".db", ".log", ".jsonl", ".pyc"))
            or name in LOCAL_FILES
            or name.startswith("docs/incidents/")
        ):
            rejected.append(name + " (local artifact)")
            continue
        # Check staged bytes, not ignored files or unstaged credentials in the workspace.
        data = subprocess.check_output(["git", "show", ":" + name], cwd=ROOT)
        if SECRET.search(data):
            rejected.append(name + " (credential pattern)")
        checked += 1
    if rejected:
        print("Repository check failed:\n" + "\n".join(rejected))
        return 1
    print(
        f"Repository check passed: {checked} tracked files; no local artifacts or recognized keys."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
