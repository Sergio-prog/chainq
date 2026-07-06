import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated

import httpx
import typer

from chainq import __version__
from chainq.errors import ChainqError

PYPI_URL = "https://pypi.org/pypi/chainq/json"
RAW_PYPROJECT_URL = "https://raw.githubusercontent.com/Sergio-prog/chainq/main/pyproject.toml"
STATE_FILE = Path.home() / ".cache" / "chainq" / "update-check.json"
CHECK_INTERVAL_SECONDS = 24 * 3600


def parse_version(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.strip().split(".")[:3])
    except ValueError:
        return (0,)


def fetch_latest_version() -> str | None:
    try:
        resp = httpx.get(PYPI_URL, timeout=5)
        if resp.status_code == 200:
            return resp.json()["info"]["version"]
    except Exception:
        pass
    try:
        resp = httpx.get(RAW_PYPROJECT_URL, timeout=5, follow_redirects=True)
        if resp.status_code == 200:
            for line in resp.text.splitlines():
                if line.strip().startswith("version") and '"' in line:
                    return line.split('"')[1]
    except Exception:
        pass
    return None


def _read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _write_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state))
    except OSError:
        pass


def run_background_check() -> None:
    state = _read_state()
    state["checked_at"] = time.time()
    latest = fetch_latest_version()
    if latest:
        state["latest"] = latest
    _write_state(state)


def maybe_remind() -> None:
    if os.environ.get("CHAINQ_NO_UPDATE_CHECK"):
        return
    state = _read_state()
    now = time.time()
    latest = state.get("latest")
    if (
        latest
        and parse_version(latest) > parse_version(__version__)
        and now - state.get("reminded_at", 0) > CHECK_INTERVAL_SECONDS
    ):
        print(f"chainq {latest} is available (you have {__version__}) — run `chainq update`", file=sys.stderr)
        state["reminded_at"] = now
        _write_state(state)
    if now - state.get("checked_at", 0) > CHECK_INTERVAL_SECONDS:
        state["checked_at"] = now
        _write_state(state)
        try:
            subprocess.Popen(
                [sys.executable, "-m", "chainq.update"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            pass


def _upgrade_command() -> list[str]:
    prefix = sys.prefix
    if "uv/tools" in prefix and shutil.which("uv"):
        return ["uv", "tool", "upgrade", "chainq"]
    if "pipx" in prefix and shutil.which("pipx"):
        return ["pipx", "upgrade", "chainq"]
    if "/Cellar/" in prefix and shutil.which("brew"):
        return ["brew", "upgrade", "chainq"]
    raise ChainqError(
        "could not detect how chainq was installed; reinstall with the install script or `uv tool install chainq`"
    )


def update(force: Annotated[bool, typer.Option("--force", help="reinstall even if already up to date")] = False):
    """Self-update chainq to the latest version."""
    latest = fetch_latest_version()
    if latest:
        _write_state({**_read_state(), "latest": latest, "checked_at": time.time()})
    if not force and latest and parse_version(latest) <= parse_version(__version__):
        print(f"chainq {__version__} is up to date")
        return
    cmd = _upgrade_command()
    if force and cmd[:3] == ["uv", "tool", "upgrade"]:
        cmd = ["uv", "tool", "upgrade", "--reinstall", "chainq"]
    if force and cmd[:2] == ["brew", "upgrade"]:
        cmd = ["brew", "reinstall", "chainq"]
    print(f"running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise ChainqError("upgrade command failed")


if __name__ == "__main__":
    run_background_check()
