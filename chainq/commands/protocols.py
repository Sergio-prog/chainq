import typer

from chainq.commands import aave, hl, pendle, uniswap

app = typer.Typer(no_args_is_help=True, help="Protocol integrations: Aave, Hyperliquid, Uniswap, Pendle.")
app.add_typer(hl.app, name="hl")
app.add_typer(aave.app, name="aave")
app.add_typer(uniswap.app, name="uniswap")
app.add_typer(pendle.app, name="pendle")
