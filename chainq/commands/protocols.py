import typer

from chainq.lazy import lazy_group

PROTOCOLS = (
    "hl",
    "aave",
    "morpho",
    "kamino",
    "lighter",
    "uniswap",
    "curve",
    "pendle",
    "sky",
    "ethena",
    "lido",
    "aerodrome",
    "llama",
)

app = typer.Typer(
    cls=lazy_group({name: f"chainq.commands.{name}:app" for name in PROTOCOLS}),
    no_args_is_help=True,
    help=(
        "Protocol integrations: Aave, Morpho, Kamino, Hyperliquid, Lighter, Uniswap, Curve, Pendle, Sky, "
        "Ethena, Lido, Aerodrome, DefiLlama."
    ),
)
