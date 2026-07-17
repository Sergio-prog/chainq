import json
import sys
from typing import Annotated

import httpx
import typer
from web3.exceptions import Web3Exception

from chainq import __version__, fmt, update
from chainq.commands import address, chain, config, evm, market, nft, portfolio, protocols, stables, yields
from chainq.errors import ChainqError

app = typer.Typer(
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

app.command()(chain.networks)
app.command()(chain.balance)
app.command()(chain.gas)
app.command()(chain.tx)
app.command()(chain.rpc)
app.add_typer(evm.app, name="evm")
app.command()(address.address)
app.command()(portfolio.portfolio)
app.command()(market.price)
app.command()(market.asset)
app.command()(market.search)
app.command()(market.trending)
app.command()(market.candles)
app.command()(stables.stables)
app.command()(yields.yields)
app.command()(update.update)
app.add_typer(protocols.app, name="protocols")
app.add_typer(nft.app, name="nft")
app.add_typer(config.app, name="config")


@app.command()
def version():
    """Print chainq version."""
    print(__version__)


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


def run():
    try:
        update.maybe_remind()
        app()
    except ChainqError as exc:
        _fail(str(exc))
    except httpx.HTTPError as exc:
        _fail(f"http request failed: {exc}")
    except Web3Exception as exc:
        _fail(f"rpc request failed: {exc}")
