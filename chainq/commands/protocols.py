import typer

from chainq.commands import aave, hl

app = typer.Typer(no_args_is_help=True, help="Protocol integrations: Aave, Hyperliquid.")
app.add_typer(hl.app, name="hl")
app.add_typer(aave.app, name="aave")
