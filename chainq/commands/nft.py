from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_amount, fmt_usd
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import coingecko, opensea

app = typer.Typer(no_args_is_help=True, help="NFT collections via OpenSea: floors, stats, top lists.")

TOP_SORT = {
    "volume": "one_day_volume",
    "7d-volume": "seven_day_volume",
    "market-cap": "market_cap",
    "owners": "num_owners",
}


def _intervals(stats: dict) -> dict[str, dict]:
    return {i.get("interval"): i for i in stats.get("intervals") or []}

def _floor_usd(floor: float | None, symbol: str | None) -> float | None:
    if floor is None or not symbol:
        return None
    price = coingecko.try_price_usd(coingecko.SYMBOL_TO_ID.get(symbol.lower()))
    return floor * price if price is not None else None


def _stats_row(slug: str, stats: dict) -> dict:
    total = stats.get("total") or {}
    intervals = _intervals(stats)
    floor = total.get("floor_price")
    symbol = total.get("floor_price_symbol") or "ETH"
    return {
        "collection": slug,
        "floor_price": floor,
        "floor_symbol": symbol,
        "floor_usd": _floor_usd(floor, symbol),
        "volume_24h": (intervals.get("one_day") or {}).get("volume"),
        "sales_24h": (intervals.get("one_day") or {}).get("sales"),
        "volume_7d": (intervals.get("seven_day") or {}).get("volume"),
        "volume_30d": (intervals.get("thirty_day") or {}).get("volume"),
        "volume_total": total.get("volume"),
        "sales_total": total.get("sales"),
        "owners": total.get("num_owners"),
    }


def _floor_text(r: dict) -> str:
    if r["floor_price"] is None:
        return "floor n/a"
    text = f"floor {fmt_amount(r['floor_price'])} {r['floor_symbol']}"
    if r["floor_usd"] is not None:
        text += f" (~{fmt_usd(r['floor_usd'])})"
    return text


def _vol(value: float | None, symbol: str) -> str:
    return f"{fmt_amount(value)} {symbol}" if value is not None else "n/a"


def _count(value: int | None) -> str:
    return f"{value:,}" if value is not None else "n/a"


@app.command()
def floor(
    collections: Annotated[list[str], typer.Argument(help="OpenSea collection slug(s), e.g. pudgypenguins")],
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Floor price and volume for one or more collections."""
    out = Out(json_out, quiet, verbose, format)
    rows = [_stats_row(slug.strip().lower(), opensea.stats(slug)) for slug in collections]
    lines = [
        f"{r['collection']}: {_floor_text(r)}  24h vol {_vol(r['volume_24h'], r['floor_symbol'])}  "
        f"owners {_count(r['owners'])}"
        for r in rows
    ]
    out.emit(
        rows,
        lines,
        quiet_value="\n".join(str(r["floor_price"]) for r in rows),
        verbose_lines=[
            f"{r['collection']}: 7d vol {_vol(r['volume_7d'], r['floor_symbol'])}, "
            f"30d vol {_vol(r['volume_30d'], r['floor_symbol'])}, "
            f"total vol {_vol(r['volume_total'], r['floor_symbol'])}, sales {_count(r['sales_total'])}"
            for r in rows
        ],
    )


@app.command()
def collection(
    slug: Annotated[str, typer.Argument(help="OpenSea collection slug, e.g. pudgypenguins")],
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Full collection profile: floor, supply, owners, volumes, contract."""
    out = Out(json_out, quiet, verbose, format)
    slug = slug.strip().lower()
    info = opensea.collection(slug)
    row = _stats_row(slug, opensea.stats(slug))
    contracts = [f"{c.get('chain')}:{c.get('address')}" for c in info.get("contracts") or []]
    data = {
        "name": info.get("name"),
        **row,
        "total_supply": info.get("total_supply"),
        "verified": info.get("safelist_status") == "verified",
        "category": info.get("category"),
        "contracts": contracts,
        "created_date": info.get("created_date"),
        "opensea_url": info.get("opensea_url"),
        "project_url": info.get("project_url") or None,
        "twitter": info.get("twitter_username") or None,
    }
    symbol = row["floor_symbol"]
    badges = ", ".join(b for b in ("verified" if data["verified"] else "", data["category"] or "") if b)
    lines = [
        f"{data['name']} ({slug})" + (f" — {badges}" if badges else ""),
        f"  {_floor_text(row)} · owners {_count(row['owners'])} · supply {_count(data['total_supply'])}",
        f"  volume: 24h {_vol(row['volume_24h'], symbol)} · 7d {_vol(row['volume_7d'], symbol)} · "
        f"30d {_vol(row['volume_30d'], symbol)} · total {_vol(row['volume_total'], symbol)}",
        f"  {data['opensea_url']}",
    ]
    out.emit(
        data,
        lines,
        quiet_value=row["floor_price"],
        verbose_lines=[
            f"contracts: {', '.join(contracts) or 'n/a'}",
            f"created: {data['created_date']}, total sales: {_count(row['sales_total'])}",
            *([f"project: {data['project_url']}"] if data["project_url"] else []),
            *([f"twitter: @{data['twitter']}"] if data["twitter"] else []),
        ],
    )


@app.command()
def top(
    sort: Annotated[str, typer.Option("--sort", "-s", help="volume | 7d-volume | market-cap | owners")] = "volume",
    limit: Annotated[int, typer.Option("--limit", "-l")] = 10,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Top collections ranked by OpenSea (requires an OpenSea API key)."""
    out = Out(json_out, quiet, verbose, format)
    if sort not in TOP_SORT:
        raise ChainqError(f"unknown sort '{sort}' (use: {', '.join(TOP_SORT)})")
    listed = opensea.top_collections(TOP_SORT[sort], limit)
    if not listed:
        raise ChainqError("OpenSea returned no collections")
    slugs = [c.get("collection") for c in listed if c.get("collection")][:limit]
    with ThreadPoolExecutor(max_workers=8) as pool:
        stat_rows = list(pool.map(lambda s: _stats_row(s, opensea.stats(s)), slugs))
    names = {c.get("collection"): c.get("name") for c in listed}
    rows = [{"name": names.get(r["collection"]), **r} for r in stat_rows]
    lines = [
        f"{i}. {r['name'] or r['collection']}: {_floor_text(r)}  24h vol {_vol(r['volume_24h'], r['floor_symbol'])}"
        for i, r in enumerate(rows, 1)
    ]
    out.emit(
        rows,
        lines,
        quiet_value="\n".join(r["collection"] for r in rows),
        verbose_lines=[
            f"{r['collection']}: owners {_count(r['owners'])}, total vol {_vol(r['volume_total'], r['floor_symbol'])}"
            for r in rows
        ],
    )
