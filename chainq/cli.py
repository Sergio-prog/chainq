import json
import os
import signal
import sys
from typing import Annotated

import typer

from chainq import __version__, fmt, progress
from chainq.errors import ChainqError
from chainq.lazy import lazy_group

COMMANDS = {
    "networks": "chainq.commands.chain:networks",
    "balance": "chainq.commands.chain:balance",
    "gas": "chainq.commands.chain:gas",
    "tx": "chainq.commands.chain:tx",
    "rpc": "chainq.commands.chain:rpc",
    "evm": "chainq.commands.evm:app",
    "address": "chainq.commands.address:address",
    "portfolio": "chainq.commands.portfolio:portfolio",
    "price": "chainq.commands.market:price",
    "asset": "chainq.commands.market:asset",
    "search": "chainq.commands.market:search",
    "trending": "chainq.commands.market:trending",
    "candles": "chainq.commands.market:candles",
    "stables": "chainq.commands.stables:stables",
    "yields": "chainq.commands.yields:yields",
    "buybacks": "chainq.commands.buybacks:buybacks",
    "etf": "chainq.commands.etf:etf",
    "update": "chainq.update:update",
    "protocols": "chainq.commands.protocols:app",
    "nft": "chainq.commands.nft:app",
    "tokens": "chainq.commands.tokens:app",
    "config": "chainq.commands.config:app",
}

app = typer.Typer(
    cls=lazy_group(COMMANDS),
    add_completion=True,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Agent-friendly CLI for onchain and crypto market data. Every command supports --json, -q, -v.",
)


def _print_version(value: bool):
    if value:
        print(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool, typer.Option("--version", help="print version and exit", callback=_print_version, is_eager=True)
    ] = False,
    no_color: Annotated[
        bool, typer.Option("--no-color", help="disable colors in text output (NO_COLOR env works too)")
    ] = False,
):
    if no_color:
        fmt.disable_colors()


@app.command()
def version():
    """Print chainq version."""
    print(__version__)


@app.command()
def help(ctx: typer.Context):
    """Show top-level help (same as `chainq --help`)."""
    print(ctx.parent.get_help())


def _wants_json() -> bool:
    args = sys.argv[1:]
    if "--json" in args:
        return True
    for i, arg in enumerate(args):
        if arg in ("--format", "-f") and i + 1 < len(args) and args[i + 1] == "json":
            return True
        if arg in ("--format=json", "-f=json"):
            return True
    return False


def _fail(message: str) -> None:
    if _wants_json():
        print(json.dumps({"error": message}))
    else:
        print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def _abort(*_: object) -> None:
    progress.clear_line()
    print("interrupted", file=sys.stderr, flush=True)
    os._exit(130)


def _is_web3_error(exc: Exception) -> bool:
    web3_exceptions = sys.modules.get("web3.exceptions")
    return web3_exceptions is not None and isinstance(exc, web3_exceptions.Web3Exception)


def _is_http_error(exc: Exception) -> bool:
    httpx = sys.modules.get("httpx")
    return httpx is not None and isinstance(exc, httpx.HTTPError)


def run():
    signal.signal(signal.SIGINT, _abort)
    try:
        from chainq import update


        update.maybe_remind()
        app()
    except ChainqError as exc:
        _fail(str(exc))
    except Exception as exc:
        if _is_http_error(exc):
            _fail(f"http request failed: {exc}")
        if _is_web3_error(exc):
            _fail(f"rpc request failed: {exc}")
        if os.environ.get("CHAINQ_DEBUG"):
            raise
        _fail(f"unexpected {type(exc).__name__}: {exc} (set CHAINQ_DEBUG=1 for a traceback)")
