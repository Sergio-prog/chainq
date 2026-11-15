import os
from dataclasses import dataclass
from pathlib import Path

from chainq.errors import ChainqError

CONFIG_PATH = Path.home() / ".config" / "chainq" / ".env"
ENV_FILES = (CONFIG_PATH, Path(".env"))


def parse_env_file(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        values[key.strip().upper()] = value
    return values


def export_env_files(paths: tuple[Path, ...] | None = None) -> None:
    merged: dict[str, str] = {}
    for path in ENV_FILES if paths is None else paths:
        merged.update(parse_env_file(path))
    for key, value in merged.items():
        os.environ.setdefault(key, value)


def _env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ChainqError(f"{name} must be a number of seconds, got '{raw}' (fix it with `chainq config set`)") from exc


@dataclass
class Settings:
    coingecko_api_key: str | None
    opensea_api_key: str | None
    asset_links: str | None
    http_timeout: float
    rpc_timeout: float
    no_update_check: bool


def load_settings() -> Settings:
    export_env_files()
    return Settings(
        coingecko_api_key=_env("CHAINQ_COINGECKO_API_KEY", "COINGECKO_API_KEY"),
        opensea_api_key=_env("CHAINQ_OPENSEA_API_KEY", "OPENSEA_API_KEY"),
        asset_links=_env("CHAINQ_ASSET_LINKS", "ASSET_LINKS"),
        http_timeout=_env_float("CHAINQ_HTTP_TIMEOUT", 10.0),
        rpc_timeout=_env_float("CHAINQ_RPC_TIMEOUT", 6.0),
        no_update_check=_env("CHAINQ_NO_UPDATE_CHECK") is not None,
    )


settings = load_settings()
