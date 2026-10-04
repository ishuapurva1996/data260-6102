"""Local, secret-free provenance for separately retained Part 3 runs."""
import hashlib
import importlib.metadata
import platform
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[3]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def provenance(module, argv):
    """Capture source bytes as well as HEAD, including truthful dirty-tree state."""
    def git(*args):
        return subprocess.check_output(["git", "-C", str(REPOSITORY), *args], text=True).strip()

    source_files = sorted([
        *REPOSITORY.glob("src/rental_tools/*.py"),
        REPOSITORY / "src/mcp_servers/rentals.py",
        *REPOSITORY.glob("scripts/hw05/part3/*.py"),
    ])
    versions = {"python": platform.python_version(), "platform": platform.platform()}
    for package in ("mcp", "pydantic", "PyMySQL", "SQLAlchemy"):
        versions[package] = importlib.metadata.version(package)
    return {
        "source": {
            "git_revision": git("rev-parse", "HEAD"),
            "dirty": bool(git("status", "--porcelain", "--untracked-files=all")),
            "sha256": {str(path.relative_to(REPOSITORY)): sha256_file(path) for path in source_files},
        },
        "versions": versions,
        "working_directory": str(Path.cwd()),
        "command": shlex.join([sys.executable, "-m", module, *argv]),
    }
