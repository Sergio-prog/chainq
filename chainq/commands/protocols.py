import typer

from chainq.commands import aave, ethena, hl, lighter, llama, morpho, pendle, sky, uniswap

app = typer.Typer(
    no_args_is_help=True,
    help="Protocol integrations: Aave, Morpho, Hyperliquid, Lighter, Uniswap, Pendle, Sky, Ethena, DefiLlama.",
)
app.add_typer(hl.app, name="hl")
app.add_typer(aave.app, name="aave")
app.add_typer(morpho.app, name="morpho")
app.add_typer(lighter.app, name="lighter")
app.add_typer(uniswap.app, name="uniswap")
app.add_typer(pendle.app, name="pendle")
app.add_typer(sky.app, name="sky")
app.add_typer(ethena.app, name="ethena")
app.add_typer(llama.app, name="llama")
