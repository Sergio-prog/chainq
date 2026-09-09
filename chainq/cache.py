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


BLOB_DIR = CACHE_DIR / "blobs"


def _blob_path(name: str) -> Path:
    return BLOB_DIR / f"{name}.json"


def get_blob(name: str, max_age: float | None = None) -> object | None:
    try:
        entry = json.loads(_blob_path(name).read_text())
        fetched_at = float(entry["fetched_at"])
        value = entry["value"]
    except Exception:
        return None
    if max_age is not None and time.time() - fetched_at > max_age:
        return None
    return value


def blob_age(name: str) -> float | None:
    try:
        return time.time() - float(json.loads(_blob_path(name).read_text())["fetched_at"])
    except Exception:
        return None


def put_blob(name: str, value: object) -> None:
    try:
        BLOB_DIR.mkdir(parents=True, exist_ok=True)
        path = _blob_path(name)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"fetched_at": time.time(), "value": value}, default=str))
        tmp.replace(path)
    except OSError:
        pass


def drop_blob(name: str) -> None:
    try:
        _blob_path(name).unlink()
    except OSError:
        pass
