import hashlib
import json
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "chainq"
CACHE_FILE = CACHE_DIR / "http-cache.json"


def key_for(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _load() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text())
    except Exception:
        return {}


def _store(data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, default=str))
    tmp.replace(CACHE_FILE)


def get(key: str) -> object | None:
    entry = _load().get(key)
    if entry and entry.get("expires_at", 0) > time.time():
        return entry["value"]
    return None


def put(key: str, value: object, ttl: float) -> None:
    now = time.time()
    data = {k: v for k, v in _load().items() if v.get("expires_at", 0) > now}
    data[key] = {"expires_at": now + ttl, "value": value}
    try:
        _store(data)
    except OSError:
        pass
