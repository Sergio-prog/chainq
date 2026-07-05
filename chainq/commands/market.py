from datetime import UTC, datetime
from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_pct, fmt_usd, humanize_usd
from chainq.networks import resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import coingecko, uniswap

SLUG_TO_NETWORK = {slug: key for key, slug in uniswap.CHAIN_SLUGS.items()}


def _dexscreener_best_pair(address: str, network_key: str | None) -> dict | None:
    pairs = [
        p
        for p in uniswap.token_pairs(address)
        if ((p.get("baseToken") or {}).get("address") or "").lower() == address.lower()
        and (network_key is None or p.get("chainId") == uniswap.CHAIN_SLUGS.get(network_key))
    ]
    if not pairs:
        return None
    return max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)


def _dexscreener_price_row(address: str, best: dict) -> dict:
    return {
        "id": None,
        "symbol": best["baseToken"]["symbol"],
        "name": best["baseToken"].get("name"),
        "contract_address": address,
        "chain": best.get("chainId"),
        "price_usd": float(best["priceUsd"]) if best.get("priceUsd") else None,
        "change_24h_pct": (best.get("priceChange") or {}).get("h24"),
        "market_cap_usd": best.get("marketCap") or best.get("fdv"),
        "market_cap_rank": None,
        "volume_24h_usd": (best.get("volume") or {}).get("h24"),
        "source": "dexscreener",
    }


def _locate_contract(address: str, network_key: str | None) -> tuple[dict | None, dict | None]:
    best_pair = _dexscreener_best_pair(address, network_key)
    lookup_key = network_key or (SLUG_TO_NETWORK.get(best_pair.get("chainId")) if best_pair else None)
    coin = None
    try:
        coin = coingecko.by_contract(address, lookup_key) if (lookup_key or best_pair is None) else None
    except ChainqError:
        if best_pair is None:
            raise
    return coin, best_pair


def _resolve_coin_id(query: str, network_key: str | None) -> str:
    if coingecko.is_address(query):
        coin, _ = _locate_contract(query, network_key)
        if coin is None:
            raise ChainqError(f"no CoinGecko asset for contract {query}; historical data needs a listed asset")
        return coin["id"]
    return coingecko.resolve_id(query)


def _to_ddmmyyyy(date: str) -> str:
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(date, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    raise ChainqError(f"could not parse date '{date}' (use YYYY-MM-DD)")


def _price_at(out: Out, assets: list[str], network_key: str | None, at: str):
    ddmmyyyy = _to_ddmmyyyy(at)
    iso = datetime.strptime(ddmmyyyy, "%d-%m-%Y").strftime("%Y-%m-%d")
    data, lines, quiet_values = [], [], []
    for query in assets:
        coin_id = _resolve_coin_id(query, network_key)
        md = (coingecko.history(coin_id, ddmmyyyy) or {}).get("market_data")
        price_usd = (md or {}).get("current_price", {}).get("usd")
        if price_usd is None:
            raise ChainqError(f"no price for '{query}' on {iso} (CoinGecko public API covers the last 365 days)")
        row = {
            "id": coin_id,
            "symbol": query.upper() if coingecko.is_address(query) else query.lower(),
            "date": iso,
            "price_usd": price_usd,
            "market_cap_usd": (md or {}).get("market_cap", {}).get("usd"),
            "volume_24h_usd": (md or {}).get("total_volume", {}).get("usd"),
            "source": "coingecko",
        }
        data.append(row)
        line = f"{coin_id} on {iso}: {fmt_usd(price_usd)}"
        if row["market_cap_usd"]:
            line += f"  mcap {humanize_usd(row['market_cap_usd'])}"
        lines.append(line)
        quiet_values.append(str(price_usd))
    out.emit(data if len(data) > 1 else data[0], lines, quiet_value="\n".join(quiet_values))


def price(
    assets: Annotated[list[str], typer.Argument(help="asset symbols, CoinGecko ids, or token contract addresses")],
    network: Annotated[str | None, typer.Option("--network", "-n", help="network hint for contract addresses")] = None,
    at: Annotated[str | None, typer.Option("--at", help="historical date (YYYY-MM-DD, within last 365 days)")] = None,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Spot price, 24h change, and market cap for one or more assets."""
    out = Out(json_out, quiet, verbose, format)
    network_key = resolve_network(network).key if network else None
    if at:
        _price_at(out, assets, network_key, at)
        return
    entries: list[tuple[str, str | None, dict | None]] = []
    ids = []
    for query in assets:
        if coingecko.is_address(query):
            coin, best_pair = _locate_contract(query, network_key)
            if coin:
                entries.append((query, coin["id"], None))
                ids.append(coin["id"])
            elif best_pair is not None:
                entries.append((query, None, _dexscreener_price_row(query, best_pair)))
            else:
                raise ChainqError(f"no asset found for contract {query} on CoinGecko or DexScreener")
        else:
            coin_id = coingecko.resolve_id(query)
            entries.append((query, coin_id, None))
            ids.append(coin_id)
    rows = {m["id"]: m for m in coingecko.markets(ids)} if ids else {}
    data, lines, quiet_values, verbose_lines = [], [], [], []
    for query, coin_id, fallback in entries:
        if fallback is not None:
            data.append(fallback)
            line = f"{fallback['symbol'].upper()} ({fallback['name']}): {fmt_usd(fallback['price_usd'] or 0)}  " \
                f"24h {fmt_pct(fallback['change_24h_pct'])}"
            if fallback.get("market_cap_usd"):
                line += f"  mcap {humanize_usd(fallback['market_cap_usd'])}"
            lines.append(line + f"  [dexscreener/{fallback['chain']}]")
            quiet_values.append(str(fallback["price_usd"]))
            verbose_lines.append(f"{fallback['symbol'].upper()}: contract {query}, best pair by liquidity [dexscreener]")
            continue
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
    query: Annotated[str, typer.Argument(help="asset symbol, CoinGecko id, or token contract address")],
    network: Annotated[str | None, typer.Option("--network", "-n", help="network hint for contract addresses")] = None,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Detailed asset profile: price, caps, supply, ATH, links."""
    out = Out(json_out, quiet, verbose, format)
    if coingecko.is_address(query):
        network_key = resolve_network(network).key if network else None
        c, _ = _locate_contract(query, network_key)
        if c is None:
            raise ChainqError(f"no CoinGecko asset for contract {query}; `chainq price {query}` falls back to DexScreener")
    else:
        c = coingecko.coin(coingecko.resolve_id(query))
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


def candles(
    asset: Annotated[str, typer.Argument(help="asset symbol, CoinGecko id, or token contract address")],
    days: Annotated[int, typer.Option("--days", "-d", help="lookback window in days")] = 30,
    network: Annotated[str | None, typer.Option("--network", "-n", help="network hint for contract addresses")] = None,
    limit: Annotated[int, typer.Option("--limit", "-l", help="show only the most recent N candles (0 = all)")] = 0,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """OHLC candles for an asset (CoinGecko); granularity auto-scales with --days."""
    out = Out(json_out, quiet, verbose, format)
    network_key = resolve_network(network).key if network else None
    coin_id = _resolve_coin_id(asset, network_key)
    effective_days = coingecko.snap_ohlc_days(days)
    raw = coingecko.ohlc(coin_id, effective_days)
    if not raw:
        raise ChainqError(f"no OHLC data for '{asset}' (resolved to '{coin_id}')")
    candles_data = [
        {
            "time": datetime.fromtimestamp(ts / 1000, UTC).strftime("%Y-%m-%d %H:%M"),
            "open": o,
            "high": h,
            "low": low,
            "close": close,
        }
        for ts, o, h, low, close in raw
    ]
    span_hours = (raw[1][0] - raw[0][0]) / 3_600_000 if len(raw) > 1 else 0
    granularity = f"{int(span_hours)}h" if span_hours < 24 else f"{int(span_hours / 24)}d"
    first, last = raw[0], raw[-1]
    change = (last[4] / first[1] - 1) * 100 if first[1] else None
    high = max(c[2] for c in raw)
    low = min(c[3] for c in raw)
    shown = candles_data[-limit:] if limit else candles_data
    summary = {
        "id": coin_id,
        "days": effective_days,
        "granularity": granularity,
        "candle_count": len(candles_data),
        "open_usd": first[1],
        "close_usd": last[4],
        "change_pct": change,
        "high_usd": high,
        "low_usd": low,
        "candles": shown,
        "source": "coingecko",
    }
    lines = [
        f"{coin_id} {effective_days}d ({granularity} candles): "
        f"{fmt_usd(first[1])} → {fmt_usd(last[4])} ({fmt_pct(change)}), "
        f"high {fmt_usd(high)}, low {fmt_usd(low)}, {len(candles_data)} candles"
    ]
    lines += [
        f"  {c['time']}  O {fmt_usd(c['open'])}  H {fmt_usd(c['high'])}  L {fmt_usd(c['low'])}  C {fmt_usd(c['close'])}"
        for c in shown
    ]
    out.emit(
        summary,
        lines,
        quiet_value=last[4],
        verbose_lines=[f"coingecko id: {coin_id}", f"requested {days}d, snapped to {effective_days}d"],
    )
