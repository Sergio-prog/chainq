import time
from datetime import UTC, datetime
from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_amount, fmt_pct, fmt_usd, humanize_usd, short_addr
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import hyperliquid
from chainq.rpc import resolve_address

app = typer.Typer(no_args_is_help=True, help="Hyperliquid public market data (perps, spot, builder dexs, outcomes).")
spot_app = typer.Typer(no_args_is_help=True, help="Hyperliquid spot markets and balances.")
app.add_typer(spot_app, name="spot")

DexOpt = Annotated[str, typer.Option("--dex", "-d", help="HIP-3 builder dex name (see `hl dexs`); empty = main dex")]


def _market_line(m: dict) -> str:
    return (
        f"{m['coin']}-PERP: mark {fmt_usd(m['mark_price'])}  24h {fmt_pct(m['change_24h_pct'])}  "
        f"vol {humanize_usd(m['volume_24h_usd'])}  OI {humanize_usd(m['open_interest_usd'])}  "
        f"funding {fmt_pct(m['funding_hourly_pct'], decimals=4)}/h ({fmt_pct(m['funding_apr_pct'], decimals=1)} APR)"
    )


def _find(markets: list[dict], coins: list[str]) -> list[dict]:
    by_coin = {m["coin"].upper(): m for m in markets}
    by_short = {m["coin"].split(":")[-1].upper(): m for m in markets}
    selected = []
    for coin in coins:
        m = by_coin.get(coin.upper()) or by_short.get(coin.upper())
        if m is None:
            raise ChainqError(f"no Hyperliquid perp market for '{coin}'")
        selected.append(m)
    return selected


@app.command()
def price(
    coins: Annotated[list[str], typer.Argument(help="perp coins, e.g. BTC ETH HYPE (or xyz:TSLA / TSLA with --dex xyz)")],
    dex: DexOpt = "",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Mark price, 24h change, volume, OI, and funding for perp markets."""
    out = Out(json_out, quiet, verbose, format)
    selected = _find(hyperliquid.perp_markets(dex), coins)
    out.emit(
        selected,
        [_market_line(m) for m in selected],
        quiet_value="\n".join(str(m["mark_price"]) for m in selected),
        verbose_lines=[
            f"{m['coin']}: oracle {fmt_usd(m['oracle_price'])}, mid {fmt_usd(m['mid_price']) if m['mid_price'] else 'n/a'}, "
            f"max leverage {m['max_leverage']}x, OI {fmt_amount(m['open_interest'])} {m['coin']}"
            for m in selected
        ],
    )


@app.command()
def markets(
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    sort: Annotated[str, typer.Option("--sort", "-s", help="volume | oi | funding | change")] = "volume",
    dex: DexOpt = "",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Top perp markets ranked by volume, OI, funding, or 24h change."""
    out = Out(json_out, quiet, verbose, format)
    keys = {
        "volume": lambda m: m["volume_24h_usd"],
        "oi": lambda m: m["open_interest_usd"],
        "funding": lambda m: abs(m["funding_hourly_pct"]),
        "change": lambda m: abs(m["change_24h_pct"] or 0),
    }
    if sort not in keys:
        raise ChainqError(f"unknown sort '{sort}' (use: {', '.join(keys)})")
    ranked = sorted(hyperliquid.perp_markets(dex), key=keys[sort], reverse=True)[:limit]
    out.emit(
        ranked,
        [_market_line(m) for m in ranked],
        quiet_value="\n".join(m["coin"] for m in ranked),
    )


def _funding_history(out: Out, coins: list[str], days: int, dex: str):
    start = int((time.time() - days * 86400) * 1000)
    rows = []
    for coin in coins:
        series = hyperliquid.funding_history(coin, start, dex)
        if not series:
            raise ChainqError(f"no funding history for '{coin}' over the last {days}d")
        rates = [float(p["fundingRate"]) for p in series]
        cumulative = sum(rates)
        mean_hourly = cumulative / len(rates)
        rows.append(
            {
                "coin": coin.upper(),
                "days": days,
                "samples": len(rates),
                "cumulative_pct": cumulative * 100,
                "mean_hourly_pct": mean_hourly * 100,
                "annualized_apr_pct": mean_hourly * 24 * 365 * 100,
                "min_hourly_pct": min(rates) * 100,
                "max_hourly_pct": max(rates) * 100,
                "start": datetime.fromtimestamp(series[0]["time"] / 1000, UTC).strftime("%Y-%m-%d %H:%M"),
                "end": datetime.fromtimestamp(series[-1]["time"] / 1000, UTC).strftime("%Y-%m-%d %H:%M"),
            }
        )
    lines = [
        f"{r['coin']}-PERP funding {r['days']}d: cumulative {fmt_pct(r['cumulative_pct'], decimals=4)}  "
        f"mean {fmt_pct(r['mean_hourly_pct'], decimals=4)}/h ({fmt_pct(r['annualized_apr_pct'], decimals=1)} APR)  "
        f"range [{r['min_hourly_pct']:+.4f}, {r['max_hourly_pct']:+.4f}]%/h  {r['samples']} samples"
        for r in rows
    ]
    out.emit(
        rows if len(rows) > 1 else rows[0],
        lines,
        quiet_value="\n".join(str(r["annualized_apr_pct"]) for r in rows),
        verbose_lines=[f"{r['coin']}: {r['start']} → {r['end']}" for r in rows],
    )


@app.command()
def funding(
    coins: Annotated[list[str] | None, typer.Argument(help="perp coins; omit for top by |rate|")] = None,
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    history: Annotated[bool, typer.Option("--history", "-H", help="historical funding over --days")] = False,
    days: Annotated[int, typer.Option("--days", "-D", help="lookback window for --history")] = 7,
    dex: DexOpt = "",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Current hourly funding rates and annualized APR (--history for a lookback window)."""
    out = Out(json_out, quiet, verbose, format)
    if history:
        if not coins:
            raise ChainqError("--history needs at least one coin, e.g. `hl funding BTC --history`")
        _funding_history(out, coins, days, dex)
        return
    all_markets = hyperliquid.perp_markets(dex)
    if coins:
        selected = _find(all_markets, coins)
    else:
        selected = sorted(all_markets, key=lambda m: abs(m["funding_hourly_pct"]), reverse=True)[:limit]
    lines = [
        f"{m['coin']}-PERP funding: {fmt_pct(m['funding_hourly_pct'], decimals=4)}/h "
        f"({fmt_pct(m['funding_apr_pct'], decimals=1)} APR)  "
        f"mark {fmt_usd(m['mark_price'])}  OI {humanize_usd(m['open_interest_usd'])}"
        for m in selected
    ]
    out.emit(selected, lines, quiet_value="\n".join(str(m["funding_hourly_pct"]) for m in selected))


@app.command()
def positions(
    address: Annotated[str, typer.Argument(help="account address (0x...)")],
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Open perp positions and margin summary for an account."""
    out = Out(json_out, quiet, verbose, format)
    addr = resolve_address(address)
    state = hyperliquid.clearinghouse_state(addr)
    summary = state.get("marginSummary") or {}
    account_value = float(summary.get("accountValue") or 0)
    positions_data = []
    lines = [
        f"HL account {short_addr(addr)}: value {fmt_usd(account_value)}, "
        f"margin used {fmt_usd(float(summary.get('totalMarginUsed') or 0))}, "
        f"withdrawable {fmt_usd(float(state.get('withdrawable') or 0))}"
    ]
    for item in state.get("assetPositions") or []:
        p = item.get("position") or {}
        size = float(p.get("szi") or 0)
        if size == 0:
            continue
        side = "long" if size > 0 else "short"
        entry = float(p["entryPx"]) if p.get("entryPx") else None
        pnl = float(p.get("unrealizedPnl") or 0)
        roe = float(p.get("returnOnEquity") or 0) * 100
        leverage = (p.get("leverage") or {}).get("value")
        liq = float(p["liquidationPx"]) if p.get("liquidationPx") else None
        positions_data.append(
            {
                "coin": p.get("coin"),
                "side": side,
                "size": size,
                "entry_price": entry,
                "position_value_usd": float(p.get("positionValue") or 0),
                "unrealized_pnl_usd": pnl,
                "return_on_equity_pct": roe,
                "leverage": leverage,
                "liquidation_price": liq,
            }
        )
        lines.append(
            f"  {p.get('coin')}: {side} {fmt_amount(abs(size))} @ {fmt_usd(entry) if entry else 'n/a'}, "
            f"value {fmt_usd(float(p.get('positionValue') or 0))}, uPnL {fmt_usd(pnl)} ({fmt_pct(roe, decimals=1)}), "
            f"{leverage}x, liq {fmt_usd(liq) if liq else 'n/a'}"
        )
    if not positions_data:
        lines.append("  no open positions")
    data = {
        "address": addr,
        "account_value_usd": account_value,
        "total_margin_used_usd": float(summary.get("totalMarginUsed") or 0),
        "withdrawable_usd": float(state.get("withdrawable") or 0),
        "positions": positions_data,
    }
    out.emit(data, lines, quiet_value=account_value)


@app.command()
def dexs(
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """List HIP-3 builder-deployed perp dexs (use their name with --dex)."""
    out = Out(json_out, quiet, verbose, format)
    rows = [
        {
            "name": d.get("name"),
            "full_name": d.get("fullName"),
            "deployer": d.get("deployer"),
            "markets": len(d.get("assetToStreamingOiCap") or []),
        }
        for d in hyperliquid.perp_dexs()
    ]
    lines = [
        f"{r['name']}: {r['full_name'] or 'n/a'}  ({r['markets']} markets, deployer {short_addr(r['deployer'] or '')})"
        for r in rows
    ]
    out.emit(rows, lines, quiet_value="\n".join(r["name"] or "" for r in rows))


def _parse_outcome_description(description: str) -> dict:
    if ":" not in description or "|" not in description and not description.startswith("class:"):
        return {}
    parts = dict(part.split(":", 1) for part in description.split("|") if ":" in part)
    return parts if "class" in parts else {}


@app.command()
def outcomes(
    query: Annotated[str | None, typer.Argument(help="filter by name/description substring")] = None,
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """HIP-4 outcome (prediction) markets with live Yes/No prices."""
    out = Out(json_out, quiet, verbose, format)
    mids = hyperliquid.all_mids()
    rows = []
    for spec in hyperliquid.outcome_meta():
        outcome_id = spec.get("outcome")
        description = spec.get("description") or ""
        if query and query.lower() not in f"{spec.get('name', '')} {description}".lower():
            continue
        yes = mids.get(f"#{outcome_id * 10}")
        no = mids.get(f"#{outcome_id * 10 + 1}")
        parsed = _parse_outcome_description(description)
        rows.append(
            {
                "outcome": outcome_id,
                "name": spec.get("name"),
                "yes_price": float(yes) if yes else None,
                "no_price": float(no) if no else None,
                "implied_probability_pct": float(yes) * 100 if yes else None,
                "underlying": parsed.get("underlying"),
                "target_price": parsed.get("targetPrice"),
                "expiry": parsed.get("expiry"),
                "description": description[:120],
                "quote_token": spec.get("quoteToken"),
            }
        )
    rows.sort(key=lambda r: r["outcome"], reverse=True)
    rows = rows[:limit]
    if not rows:
        raise ChainqError(f"no outcome markets matching '{query}'" if query else "no outcome markets found")
    lines = []
    for r in rows:
        yes = f"Yes {r['yes_price']:.3f}" if r["yes_price"] is not None else "Yes n/a"
        no = f"No {r['no_price']:.3f}" if r["no_price"] is not None else "No n/a"
        detail = ""
        if r["underlying"] and r["target_price"]:
            detail = f"  [{r['underlying']} ≥ {r['target_price']}, exp {r['expiry']}]"
        elif r["description"] and r["description"] != r["name"]:
            detail = f"  ({r['description'][:60].rstrip()})" if not r["underlying"] else ""
        lines.append(f"#{r['outcome']} {r['name']}: {yes} / {no}{detail}")
    out.emit(rows, lines, quiet_value="\n".join(str(r["outcome"]) for r in rows))


def _spot_line(m: dict) -> str:
    mcap = f"  mcap {humanize_usd(m['market_cap_usd'])}" if m["market_cap_usd"] else ""
    price = m["mid_price"] or m["mark_price"]
    return (
        f"{m['pair']} (spot): {fmt_usd(price) if price else 'n/a'}  24h {fmt_pct(m['change_24h_pct'])}  "
        f"vol {humanize_usd(m['volume_24h_usd'])}{mcap}"
    )


def _find_spot(markets: list[dict], coins: list[str]) -> list[dict]:
    ranked = sorted(markets, key=lambda m: not m["canonical"])
    selected = []
    for coin in coins:
        needle = coin.upper()
        match = next(
            (m for m in ranked if needle in ((m["pair"] or "").upper(), (m["base"] or "").upper(), m["hl_name"].upper())),
            None,
        )
        if match is None:
            raise ChainqError(f"no Hyperliquid spot market for '{coin}'")
        selected.append(match)
    return selected


@spot_app.command(name="price")
def spot_price(
    coins: Annotated[list[str], typer.Argument(help="spot tokens or pairs, e.g. HYPE PURR/USDC")],
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Spot price, 24h change, volume, and market cap for spot pairs."""
    out = Out(json_out, quiet, verbose, format)
    selected = _find_spot(hyperliquid.spot_markets(), coins)
    out.emit(
        selected,
        [_spot_line(m) for m in selected],
        quiet_value="\n".join(str(m["mid_price"] or m["mark_price"]) for m in selected),
        verbose_lines=[
            f"{m['pair']}: mark {fmt_usd(m['mark_price']) if m['mark_price'] else 'n/a'}, "
            f"circulating {fmt_amount(m['circulating_supply']) if m['circulating_supply'] else 'n/a'} {m['base']}, "
            f"hl name {m['hl_name']}"
            for m in selected
        ],
    )


@spot_app.command(name="markets")
def spot_markets(
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Top spot markets by 24h volume."""
    out = Out(json_out, quiet, verbose, format)
    ranked = sorted(hyperliquid.spot_markets(), key=lambda m: m["volume_24h_usd"], reverse=True)[:limit]
    out.emit(ranked, [_spot_line(m) for m in ranked], quiet_value="\n".join(m["pair"] for m in ranked))


@spot_app.command(name="balances")
def spot_balances(
    address: Annotated[str, typer.Argument(help="account address (0x...)")],
    min_usd: Annotated[float, typer.Option("--min-usd", help="hide balances worth less than this")] = 0,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Spot token balances (with USD values) for an account."""
    out = Out(json_out, quiet, verbose, format)
    addr = resolve_address(address)
    balances = hyperliquid.spot_balances(addr)
    prices: dict[str, float] = {"USDC": 1.0}
    ranked = sorted(hyperliquid.spot_markets(), key=lambda m: (m["canonical"], m["volume_24h_usd"]))
    for m in ranked:
        price = m["mid_price"] or m["mark_price"]
        if m["base"] and price:
            prices[m["base"]] = price
    rows = []
    for b in balances:
        total = float(b.get("total") or 0)
        if total == 0:
            continue
        price = prices.get(b.get("coin"))
        value_usd = total * price if price is not None else None
        if value_usd is not None and value_usd < min_usd:
            continue
        rows.append(
            {
                "coin": b.get("coin"),
                "total": total,
                "hold": float(b.get("hold") or 0),
                "price_usd": price,
                "value_usd": value_usd,
            }
        )
    rows.sort(key=lambda r: r["value_usd"] or 0, reverse=True)
    total_usd = sum(r["value_usd"] or 0 for r in rows)
    lines = [f"HL spot balances {short_addr(addr)}: ~{fmt_usd(total_usd)} across {len(rows)} tokens"]
    lines.extend(
        f"  {r['coin']}: {fmt_amount(r['total'])}" + (f" (~{fmt_usd(r['value_usd'])})" if r["value_usd"] is not None else "")
        for r in rows
    )
    if not rows:
        lines.append("  no spot balances")
    out.emit(
        {"address": addr, "total_value_usd": total_usd, "balances": rows},
        lines,
        quiet_value=total_usd,
    )
