from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_pct, humanize_usd
from chainq.networks import resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import pendle

app = typer.Typer(no_args_is_help=True, help="Pendle yield markets.")

SORT_KEYS = {
    "liquidity": lambda m: m["liquidity_usd"] or 0,
    "implied-apy": lambda m: m["implied_apy_pct"] or 0,
    "expiry": lambda m: -(m["days_to_expiry"] or 0),
}


def _market_line(m: dict) -> str:
    implied = fmt_pct(m["implied_apy_pct"], signed=False)
    lp = fmt_pct(m["aggregated_apy_pct"], signed=False)
    return (
        f"{m['name']} (exp {m['expiry']}, {m['days_to_expiry']}d): implied APY {implied}  LP APY {lp}  "
        f"liquidity {humanize_usd(m['liquidity_usd'] or 0)}"
    )


@app.command()
def markets(
    network: Annotated[str, typer.Option("--network", "-n", help="network key, alias, or chain id")] = "ethereum",
    coin: Annotated[str | None, typer.Option("--coin", "-c", help="filter by market name substring")] = None,
    sort: Annotated[str, typer.Option("--sort", "-s", help="liquidity | implied-apy | expiry")] = "liquidity",
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Active Pendle markets: implied APY, LP APY, liquidity, expiry."""
    out = Out(json_out, quiet, verbose, format)
    if sort not in SORT_KEYS:
        raise ChainqError(f"unknown sort '{sort}' (use: {', '.join(SORT_KEYS)})")
    net = resolve_network(network)
    rows = [pendle.market_row(m) for m in pendle.active_markets(net.chain_id)]
    if not rows:
        raise ChainqError(f"no active Pendle markets on {net.name}")
    if coin:
        rows = [r for r in rows if coin.lower() in (r["name"] or "").lower()]
        if not rows:
            raise ChainqError(f"no Pendle market matching '{coin}' on {net.name}")
    rows = sorted(rows, key=SORT_KEYS[sort], reverse=True)[:limit]
    out.emit(
        rows,
        [_market_line(m) for m in rows],
        quiet_value="\n".join(m["name"] or "" for m in rows),
        verbose_lines=[
            f"{m['name']}: address {m['address']}, prime {m['prime']}, categories {', '.join(m['categories']) or 'n/a'}"
            for m in rows
        ],
    )
