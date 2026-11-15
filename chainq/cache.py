import hashlib
import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "chainq"
CACHE_FILE = CACHE_DIR / "http-cache.json"

_lock = threading.Lock()
_snapshot: tuple[Path, int, dict] | None = None


def key_for(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _load() -> dict:
    global _snapshot
    try:
        mtime = CACHE_FILE.stat().st_mtime_ns
        if _snapshot is not None and _snapshot[:2] == (CACHE_FILE, mtime):
            return _snapshot[2]
        data = json.loads(CACHE_FILE.read_text())
    except Exception:
        return {}
    _snapshot = (CACHE_FILE, mtime, data)
    return data


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def _store(data: dict) -> None:
    _write_atomic(CACHE_FILE, json.dumps(data, default=str))


def get(key: str) -> object | None:
    entry = _load().get(key)
    if entry and entry.get("expires_at", 0) > time.time():
        return entry["value"]
    return None


def get_many(keys: list[str]) -> dict[str, object]:
    now = time.time()
    data = _load()
    return {k: data[k]["value"] for k in keys if k in data and data[k].get("expires_at", 0) > now}


def remember[T](parts: tuple, ttl: float, compute: Callable[[], T]) -> T:
    key = key_for(*parts)
    cached = get(key)
    if cached is not None:
        return cached
    value = compute()
    if value is not None:
        put(key, value, ttl)
    return value


def put(key: str, value: object, ttl: float) -> None:
    put_many({key: value}, ttl)


def put_many(values: dict[str, object], ttl: float) -> None:
    if not values:
        return
    with _lock:
        now = time.time()
        data = {k: v for k, v in _load().items() if v.get("expires_at", 0) > now}
        data.update({key: {"expires_at": now + ttl, "value": value} for key, value in values.items()})
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
        _write_atomic(_blob_path(name), json.dumps({"fetched_at": time.time(), "value": value}, default=str))
    except OSError:
        pass


def drop_blob(name: str) -> None:
    try:
        _blob_path(name).unlink()
    except OSError:
        pass
