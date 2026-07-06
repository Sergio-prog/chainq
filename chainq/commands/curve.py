from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_pct, fmt_usd, humanize_usd
from chainq.networks import resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import curve

app = typer.Typer(no_args_is_help=True, help="Curve: stable/crypto AMM pools, TVL, volume, and APYs.")

SORT_KEYS = {
    "tvl": lambda p: p["tvl_usd"] or 0,
    "volume": lambda p: p["volume_24h_usd"] or 0,
    "apy": lambda p: p["apy_base_pct"] or 0,
}


@app.command()
def pools(
    network: Annotated[str, typer.Option("--network", "-n", help="network key, alias, or chain id")] = "ethereum",
    coin: Annotated[str | None, typer.Option("--coin", "-c", help="filter by coin symbol or pool name")] = None,
    sort: Annotated[str, typer.Option("--sort", "-s", help="tvl | volume | apy")] = "tvl",
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    min_tvl: Annotated[float, typer.Option("--min-tvl", help="hide pools with TVL below this")] = 0,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Curve pools ranked by TVL: coins, 24h volume, base and CRV APY."""
    out = Out(json_out, quiet, verbose, format)
    if sort not in SORT_KEYS:
        raise ChainqError(f"unknown sort '{sort}' (use: {', '.join(SORT_KEYS)})")
    net = resolve_network(network)
    rows = curve.pools(net.key)
    if coin:
        q = coin.strip().lower()
        rows = [
            p
            for p in rows
            if q in (p["name"] or "").lower()
            or q in (p["symbol"] or "").lower()
            or any(q == (c or "").lower() for c in p["coins"])
        ]
    rows = [p for p in rows if (p["tvl_usd"] or 0) >= min_tvl]
    rows = sorted(rows, key=SORT_KEYS[sort], reverse=True)[:limit]
    if not rows:
        raise ChainqError(f"no Curve pools found on {net.name}" + (f" for '{coin}'" if coin else ""))
    lines = []
    for p in rows:
        crv = ""
        if p["apy_crv_min_pct"]:
            crv = f" + CRV {fmt_pct(p['apy_crv_min_pct'], signed=False)}"
            if p["apy_crv_max_pct"] and p["apy_crv_max_pct"] != p["apy_crv_min_pct"]:
                crv += f"–{fmt_pct(p['apy_crv_max_pct'], signed=False)}"
        lines.append(
            f"{'/'.join(c for c in p['coins'] if c)} [{p['pool_type'] or 'pool'}]: "
            f"TVL {humanize_usd(p['tvl_usd'] or 0)}  vol {humanize_usd(p['volume_24h_usd'] or 0)}  "
            f"APY {fmt_pct(p['apy_base_pct'], signed=False)}{crv}"
        )
    out.emit(
        rows,
        lines,
        quiet_value="\n".join(p["address"] or "" for p in rows),
        verbose_lines=[f"{'/'.join(c for c in p['coins'] if c)}: {p['address']}" for p in rows],
    )


@app.command()
def stats(
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Curve protocol totals: TVL, volume, fees, crvUSD, and CRV price."""
    out = Out(json_out, quiet, verbose, format)
    data = curve.stats()
    lines = [
        f"Curve TVL: {humanize_usd(data['tvl_usd'] or 0)}"
        + (f"  crvUSD TVL: {humanize_usd(data['crvusd_tvl_usd'])}" if data["crvusd_tvl_usd"] else ""),
        f"24h volume: {humanize_usd(data['volume_24h_usd'] or 0)}  24h fees: {humanize_usd(data['fees_24h_usd'] or 0)}",
        f"CRV: {fmt_usd(data['crv_price_usd']) if data['crv_price_usd'] else 'n/a'}",
    ]
    out.emit(
        data,
        lines,
        quiet_value=data["tvl_usd"],
        verbose_lines=[
            f"7d volume: {humanize_usd(data['volume_7d_usd'] or 0)}, 7d fees: {humanize_usd(data['fees_7d_usd'] or 0)}"
        ],
    )
