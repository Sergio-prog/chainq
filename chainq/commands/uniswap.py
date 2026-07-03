from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_pct, fmt_usd, humanize_usd
from chainq.networks import resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import uniswap
from chainq.tokens import TOKENS

app = typer.Typer(no_args_is_help=True, help="Uniswap pools and protocol stats.")

SORT_KEYS = {
    "liquidity": lambda p: p["liquidity_usd"] or 0,
    "volume": lambda p: p["volume_24h_usd"] or 0,
}


def _pool_line(p: dict) -> str:
    version = f" {p['version']}" if p["version"] else ""
    price = f"  price {fmt_usd(p['price_usd'])}" if p["price_usd"] is not None else ""
    return (
        f"{p['pair']} [{p['chain']}{version}]:{price}  24h {fmt_pct(p['change_24h_pct'])}  "
        f"vol {humanize_usd(p['volume_24h_usd'] or 0)}  liquidity {humanize_usd(p['liquidity_usd'] or 0)}"
    )


@app.command()
def pools(
    query: Annotated[str, typer.Argument(help="pair like 'weth usdc' or 'weth/usdc', a token symbol, or a token address")],
    network: Annotated[str, typer.Option("--network", "-n", help="network key, alias, or chain id")] = "ethereum",
    sort: Annotated[str, typer.Option("--sort", "-s", help="liquidity | volume")] = "liquidity",
    limit: Annotated[int, typer.Option("--limit", "-l")] = 10,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Find Uniswap pools: price, 24h volume, liquidity (via DexScreener)."""
    out = Out(json_out, quiet, verbose, format)
    if sort not in SORT_KEYS:
        raise ChainqError(f"unknown sort '{sort}' (use: {', '.join(SORT_KEYS)})")
    net = resolve_network(network)
    chain_slug = uniswap.CHAIN_SLUGS.get(net.key)
    if chain_slug is None:
        raise ChainqError(f"no DexScreener mapping for {net.name}")
    parts = query.replace("/", " ").split()
    base, quote = parts[0], parts[1] if len(parts) > 1 else None
    if base.startswith("0x") and len(base) == 42:
        address = base
    else:
        address = TOKENS.get(net.key, {}).get(base.lower())
    pairs = uniswap.token_pairs(address) if address else uniswap.search_pairs(query)
    rows = sorted(uniswap.uniswap_rows(pairs, chain_slug, quote), key=SORT_KEYS[sort], reverse=True)[:limit]
    if not rows:
        raise ChainqError(f"no Uniswap pools found for '{query}' on {net.name}")
    out.emit(
        rows,
        [_pool_line(p) for p in rows],
        quiet_value="\n".join(p["pair_address"] or p["pair"] for p in rows),
        verbose_lines=[f"{p['pair']}: {p['pair_address']}  {p['url']}" for p in rows],
    )


@app.command()
def stats(
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Uniswap protocol totals: TVL and volumes (via DefiLlama)."""
    out = Out(json_out, quiet, verbose, format)
    data = uniswap.stats()
    text = (
        f"Uniswap: TVL {humanize_usd(data['tvl_usd'] or 0)}  24h vol {humanize_usd(data['volume_24h_usd'] or 0)} "
        f"({fmt_pct(data['volume_change_1d_pct'])})  7d vol {humanize_usd(data['volume_7d_usd'] or 0)}  "
        f"30d vol {humanize_usd(data['volume_30d_usd'] or 0)}"
    )
    out.emit(data, text, quiet_value=data["tvl_usd"])
