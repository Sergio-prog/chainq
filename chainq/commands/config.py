from pathlib import Path
from typing import Annotated

import typer

from chainq.errors import ChainqError

app = typer.Typer(no_args_is_help=True, help="Manage chainq configuration (stored in ~/.config/chainq/.env).")

CONFIG_PATH = Path.home() / ".config" / "chainq" / ".env"

KNOWN_KEYS = (
    "COINGECKO_API_KEY",
    "OPENSEA_API_KEY",
    "CHAINQ_HTTP_TIMEOUT",
    "CHAINQ_RPC_TIMEOUT",
    "CHAINQ_NO_UPDATE_CHECK",
    "CHAINQ_RPC_<NETWORK>",
)

SECRET_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD")


def _normalize(key: str) -> str:
    return key.strip().upper().replace("-", "_")


def _read() -> dict[str, str]:
    values: dict[str, str] = {}
    if not CONFIG_PATH.exists():
        return values
    for line in CONFIG_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _write(values: dict[str, str]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    CONFIG_PATH.chmod(0o600)


def _mask(key: str, value: str) -> str:
    if not any(marker in key for marker in SECRET_MARKERS) or key == "CHAINQ_NO_UPDATE_CHECK":
        return value
    if len(value) > 8:
        return f"{value[:4]}…{value[-4:]}"
    return "****"


@app.command(name="set")
def set_(
    key: Annotated[str, typer.Argument(help="e.g. coingecko-api-key, CHAINQ_RPC_ETHEREUM")],
    value: Annotated[str, typer.Argument()],
):
    """Set a config value (applies to every future chainq run)."""
    values = _read()
    normalized = _normalize(key)
    values[normalized] = value
    _write(values)
    print(f"{normalized}={_mask(normalized, value)}  ({CONFIG_PATH})")


@app.command()
def get(key: Annotated[str, typer.Argument()]):
    """Print one config value."""
    values = _read()
    normalized = _normalize(key)
    if normalized not in values:
        raise ChainqError(f"{normalized} is not set (see `chainq config list`)")
    print(values[normalized])


@app.command()
def unset(key: Annotated[str, typer.Argument()]):
    """Remove a config value."""
    values = _read()
    normalized = _normalize(key)
    if normalized not in values:
        raise ChainqError(f"{normalized} is not set")
    del values[normalized]
    _write(values)
    print(f"removed {normalized}")


@app.command(name="list")
def list_(show_secrets: Annotated[bool, typer.Option("--show-secrets", help="print secret values in full")] = False):
    """List configured values (secrets masked by default)."""
    values = _read()
    if not values:
        print(f"no config set ({CONFIG_PATH})")
        print(f"known keys: {', '.join(KNOWN_KEYS)}")
        return
    for key, value in values.items():
        print(f"{key}={value if show_secrets else _mask(key, value)}")


@app.command()
def path():
    """Print the config file path."""
    print(CONFIG_PATH)
