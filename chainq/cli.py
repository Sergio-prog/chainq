import sys

import httpx
import typer

from chainq import __version__
from chainq.commands import chain, hl, market
from chainq.errors import ChainqError

app = typer.Typer(
    add_completion=False,
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
app.command()(market.price)
app.command()(market.asset)
app.command()(market.search)
app.add_typer(hl.app, name="hl")


@app.command()
def version():
    """Print chainq version."""
    print(__version__)


def run():
    try:
        app()
    except ChainqError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as exc:
        print(f"error: http request failed: {exc}", file=sys.stderr)
        sys.exit(1)
