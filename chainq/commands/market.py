from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_pct, fmt_usd, humanize_usd
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import coingecko


def price(
    assets: Annotated[list[str], typer.Argument(help="asset symbols or CoinGecko ids, e.g. eth btc hype")],
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Spot price, 24h change, and market cap for one or more assets."""
    out = Out(json_out, quiet, verbose, format)
    ids = [coingecko.resolve_id(a) for a in assets]
    rows = {m["id"]: m for m in coingecko.markets(ids)}
    data, lines, quiet_values, verbose_lines = [], [], [], []
    for query, coin_id in zip(assets, ids, strict=True):
        m = rows.get(coin_id)
        if m is None:
            raise ChainqError(f"no market data for '{query}' (resolved to '{coin_id}')")
        change_24h = m.get("price_change_percentage_24h")
        change_7d = m.get("price_change_percentage_7d_in_currency")
        data.append(
            {
                "id": m["id"],
                "symbol": m["symbol"],
                "name": m["name"],
                "price_usd": m["current_price"],
                "change_24h_pct": change_24h,
                "change_7d_pct": change_7d,
                "market_cap_usd": m.get("market_cap"),
                "market_cap_rank": m.get("market_cap_rank"),
                "volume_24h_usd": m.get("total_volume"),
                "source": "coingecko",
            }
        )
        line = f"{m['symbol'].upper()} ({m['name']}): {fmt_usd(m['current_price'])}  24h {fmt_pct(change_24h)}"
        if m.get("market_cap"):
            line += f"  mcap {humanize_usd(m['market_cap'])}"
        lines.append(line)
        quiet_values.append(str(m["current_price"]))
        verbose_lines.append(
            f"{m['symbol'].upper()}: 7d {fmt_pct(change_7d)}, rank #{m.get('market_cap_rank')}, "
            f"24h vol {humanize_usd(m.get('total_volume') or 0)}, id {m['id']} [coingecko]"
        )
    out.emit(data, lines, quiet_value="\n".join(quiet_values), verbose_lines=verbose_lines)


def _money(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except ValueError:
        return None


def trending(
    limit: Annotated[int, typer.Option("--limit", "-l")] = 10,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Trending assets on CoinGecko right now."""
    out = Out(json_out, quiet, verbose, format)
    rows = []
    for entry in coingecko.trending()[:limit]:
        item = entry["item"]
        d = item.get("data") or {}
        rows.append(
            {
                "id": item["id"],
                "symbol": item["symbol"],
                "name": item["name"],
                "market_cap_rank": item.get("market_cap_rank"),
                "price_usd": _money(d.get("price")),
                "change_24h_pct": (d.get("price_change_percentage_24h") or {}).get("usd"),
                "market_cap_usd": _money(d.get("market_cap")),
                "volume_24h_usd": _money(d.get("total_volume")),
                "source": "coingecko",
            }
        )
    lines = [
        f"{i}. {r['symbol'].upper()} ({r['name']}): "
        + (fmt_usd(r["price_usd"]) if r["price_usd"] is not None else "n/a")
        + f"  24h {fmt_pct(r['change_24h_pct'])}"
        + (f"  mcap {humanize_usd(r['market_cap_usd'])}" if r["market_cap_usd"] else "")
        for i, r in enumerate(rows, start=1)
    ]
    out.emit(rows, lines, quiet_value="\n".join(r["id"] for r in rows))


def asset(
    query: Annotated[str, typer.Argument(help="asset symbol or CoinGecko id")],
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Detailed asset profile: price, caps, supply, ATH, links."""
    out = Out(json_out, quiet, verbose, format)
    coin_id = coingecko.resolve_id(query)
    c = coingecko.coin(coin_id)
    md = c["market_data"]
    price_usd = md["current_price"].get("usd")
    ath = md["ath"].get("usd")
    data = {
        "id": c["id"],
        "symbol": c["symbol"],
        "name": c["name"],
        "market_cap_rank": c.get("market_cap_rank"),
        "price_usd": price_usd,
        "change_24h_pct": md.get("price_change_percentage_24h"),
        "change_7d_pct": md.get("price_change_percentage_7d"),
        "change_30d_pct": md.get("price_change_percentage_30d"),
        "market_cap_usd": md["market_cap"].get("usd"),
        "fdv_usd": (md.get("fully_diluted_valuation") or {}).get("usd"),
        "volume_24h_usd": md["total_volume"].get("usd"),
        "circulating_supply": md.get("circulating_supply"),
        "total_supply": md.get("total_supply"),
        "max_supply": md.get("max_supply"),
        "ath_usd": ath,
        "ath_change_pct": md["ath_change_percentage"].get("usd"),
        "ath_date": md["ath_date"].get("usd"),
        "homepage": next((u for u in c.get("links", {}).get("homepage", []) if u), None),
        "categories": [cat for cat in c.get("categories") or [] if cat][:5],
        "source": "coingecko",
    }
    lines = [
        f"{c['name']} ({c['symbol'].upper()}) — rank #{data['market_cap_rank']}",
        f"  price {fmt_usd(price_usd)}  24h {fmt_pct(data['change_24h_pct'])}  "
        f"7d {fmt_pct(data['change_7d_pct'])}  30d {fmt_pct(data['change_30d_pct'])}",
        f"  mcap {humanize_usd(data['market_cap_usd'] or 0)}"
        + (f", fdv {humanize_usd(data['fdv_usd'])}" if data["fdv_usd"] else "")
        + f", 24h vol {humanize_usd(data['volume_24h_usd'] or 0)}",
        f"  supply {humanize_usd(data['circulating_supply'] or 0).removeprefix('$')} circulating"
        + (f" / {humanize_usd(data['max_supply']).removeprefix('$')} max" if data["max_supply"] else ""),
    ]
    if ath:
        lines.append(f"  ath {fmt_usd(ath)} ({fmt_pct(data['ath_change_pct'])} from ath, {str(data['ath_date'])[:10]})")
    out.emit(
        data,
        lines,
        quiet_value=price_usd,
        verbose_lines=[
            f"categories: {', '.join(data['categories']) or 'n/a'}",
            f"homepage: {data['homepage'] or 'n/a'}",
            f"coingecko id: {c['id']}",
        ],
    )


def search(
    query: Annotated[str, typer.Argument(help="free-text asset search")],
    limit: Annotated[int, typer.Option("--limit", "-l")] = 10,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Search assets on CoinGecko; returns ids usable in price/asset commands."""
    out = Out(json_out, quiet, verbose, format)
    coins = coingecko.search(query)[:limit]
    if not coins:
        raise ChainqError(f"no assets found for '{query}'")
    data = [
        {"id": c["id"], "symbol": c["symbol"], "name": c["name"], "market_cap_rank": c.get("market_cap_rank")}
        for c in coins
    ]
    lines = [
        f"{c['id']}  ({c['symbol']}) {c['name']}" + (f"  rank #{c['market_cap_rank']}" if c.get("market_cap_rank") else "")
        for c in coins
    ]
    out.emit(data, lines, quiet_value="\n".join(c["id"] for c in coins))
