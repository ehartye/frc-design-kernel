"""Library version and commit. Recorded in outputs as information only; nothing reads it back as a gate."""
import json
import subprocess
from importlib import metadata
from pathlib import Path

NAME = "frc-design-kernel"


def _installed():
    """(version, commit) of the installed package; the commit comes from pip's record of a git install."""
    try:
        dist = metadata.distribution(NAME)
    except metadata.PackageNotFoundError:
        return None, None
    commit = None
    record = dist.read_text("direct_url.json")
    if record:
        commit = json.loads(record).get("vcs_info", {}).get("commit_id")
    return dist.version, commit


def _checkout_commit():
    """The commit of a source checkout the library is running from, if any."""
    root = Path(__file__).resolve().parent.parent
    if not (root / ".git").exists():
        return None
    try:
        done = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def generator():
    """What made an output: {"library", "version", "commit"}. Unknown parts are None."""
    version, commit = _installed()
    return {"library": NAME, "version": version or "0.1.0", "commit": commit or _checkout_commit()}
