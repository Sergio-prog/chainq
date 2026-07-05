import json
import sys

import httpx
import typer

from chainq import __version__, update
from chainq.commands import chain, config, market, nft, portfolio, protocols, stables
from chainq.errors import ChainqError

app = typer.Typer(
    add_completion=True,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Agent-friendly CLI for onchain and crypto market data. Every command supports --json, -q, -v.",
)

app.command()(chain.networks)
app.command()(chain.balance)
app.command()(chain.gas)
app.command()(chain.tx)
app.command()(chain.rpc)
app.command()(portfolio.portfolio)
app.command()(market.price)
app.command()(market.asset)
app.command()(market.search)
app.command()(market.trending)
app.command()(market.candles)
app.command()(stables.stables)
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
