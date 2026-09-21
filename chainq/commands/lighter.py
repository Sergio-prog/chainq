from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import dim, fmt_amount, fmt_pct, fmt_usd, humanize_usd, short_addr
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import lighter
from chainq.rpc import resolve_address

app = typer.Typer(no_args_is_help=True, help="Lighter public market data (perps, spot).")
spot_app = typer.Typer(no_args_is_help=True, help="Lighter spot markets and balances.")
app.add_typer(spot_app, name="spot")

SORT_KEYS = {
    "volume": lambda m: m["volume_24h_usd"],
    "oi": lambda m: m["open_interest_usd"],
    "change": lambda m: abs(m["change_24h_pct"] or 0),
}


def _market_line(m: dict) -> str:
    funding = ""
    if m.get("funding_hourly_pct") is not None:
        funding = f"  funding {m['funding_hourly_pct']:+.4f}%/h ({m['funding_apr_pct']:+.1f}% APR)"
    return (
        f"{m['coin']}-PERP: last {fmt_usd(m['last_price'])}  24h {fmt_pct(m['change_24h_pct'])}  "
        f"vol {humanize_usd(m['volume_24h_usd'])}  OI {humanize_usd(m['open_interest_usd'])}{funding}"
    )


def _with_funding(markets: list[dict]) -> list[dict]:
    rates = lighter.funding_rates()
    for m in markets:
        rate = rates.get(m["coin"])
        m["funding_hourly_pct"] = rate * 100 if rate is not None else None
        m["funding_apr_pct"] = rate * 24 * 365 * 100 if rate is not None else None
    return markets


def _find(markets: list[dict], coins: list[str]) -> list[dict]:
    by_coin = {m["coin"].upper(): m for m in markets}
    selected = []
    for coin in coins:
        m = by_coin.get(coin.upper())
        if m is None:
            raise ChainqError(f"no Lighter market for '{coin}'")
        selected.append(m)
    return selected


@app.command()
def price(
    coins: Annotated[list[str], typer.Argument(help="perp coins, e.g. BTC ETH SOL")],
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Last price, 24h change, volume, OI, and funding for Lighter perps."""
    out = Out(json_out, quiet, verbose, format)
    selected = _with_funding(_find(lighter.markets(), coins))
    out.emit(
        selected,
        [_market_line(m) for m in selected],
        quiet_value="\n".join(str(m["last_price"]) for m in selected),
        verbose_lines=[
            f"{m['coin']}: market id {m['market_id']}, 24h trades {m['trades_24h']}, "
            f"OI {fmt_amount(m['open_interest'])} {m['coin']}"
            for m in selected
        ],
    )


@app.command()
def markets(
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    sort: Annotated[str, typer.Option("--sort", "-s", help="volume | oi | change")] = "volume",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Top Lighter perp markets by volume, OI, or 24h change."""
    out = Out(json_out, quiet, verbose, format)
    if sort not in SORT_KEYS:
        raise ChainqError(f"unknown sort '{sort}' (use: {', '.join(SORT_KEYS)})")
    ranked = _with_funding(sorted(lighter.markets(), key=SORT_KEYS[sort], reverse=True)[:limit])
    out.emit(ranked, [_market_line(m) for m in ranked], quiet_value="\n".join(m["coin"] for m in ranked))


@app.command()
def funding(
    coins: Annotated[list[str] | None, typer.Argument(help="perp coins; omit for top by |rate|")] = None,
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Current Lighter funding rates (hourly and annualized)."""
    out = Out(json_out, quiet, verbose, format)
    all_markets = _with_funding(lighter.markets())
    if coins:
        selected = _find(all_markets, coins)
    else:
        selected = sorted(all_markets, key=lambda m: abs(m["funding_hourly_pct"] or 0), reverse=True)[:limit]
    lines = [
        f"{m['coin']}-PERP funding: {m['funding_hourly_pct']:+.4f}%/h ({m['funding_apr_pct']:+.1f}% APR)  "
        f"last {fmt_usd(m['last_price'])}  OI {humanize_usd(m['open_interest_usd'])}"
        for m in selected
        if m["funding_hourly_pct"] is not None
    ]
    out.emit(selected, lines, quiet_value="\n".join(str(m["funding_hourly_pct"]) for m in selected))


@app.command()
def positions(
    address: Annotated[str, typer.Argument(help="L1 account address (0x...)")],
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Open Lighter positions and account balances for an address."""
    out = Out(json_out, quiet, verbose, format)
    addr = resolve_address(address)
    acc = lighter.account(addr)
    total = float(acc.get("total_asset_value") or 0)
    positions_data = []
    lines = [
        f"Lighter account {short_addr(addr)}: value {fmt_usd(total)}, "
        f"collateral {fmt_usd(float(acc.get('collateral') or 0))}, "
        f"available {fmt_usd(float(acc.get('available_balance') or 0))}"
    ]
    for p in acc.get("positions") or []:
        size = float(p.get("position") or 0)
        if size == 0:
            continue
        sign = int(p.get("sign") or 1)
        side = "long" if sign >= 0 else "short"
        entry = float(p.get("avg_entry_price") or 0)
        pnl = float(p.get("unrealized_pnl") or 0)
        liq = float(p.get("liquidation_price") or 0)
        positions_data.append(
            {
                "coin": p.get("symbol") or p.get("market_id"),
                "side": side,
                "size": size,
                "entry_price": entry or None,
                "position_value_usd": float(p.get("position_value") or 0),
                "unrealized_pnl_usd": pnl,
                "liquidation_price": liq or None,
            }
        )
        lines.append(
            f"  {positions_data[-1]['coin']}: {side} {fmt_amount(size)} @ {fmt_usd(entry) if entry else 'n/a'}, "
            f"value {fmt_usd(positions_data[-1]['position_value_usd'])}, uPnL {fmt_usd(pnl)}, "
            f"liq {fmt_usd(liq) if liq else 'n/a'}"
        )
    if not positions_data:
        lines.append("  no open positions")
    data = {
        "address": addr,
        "account_index": acc.get("account_index"),
        "total_asset_value_usd": total,
        "collateral_usd": float(acc.get("collateral") or 0),
        "available_balance_usd": float(acc.get("available_balance") or 0),
        "positions": positions_data,
    }
    out.emit(data, lines, quiet_value=total)


def _spot_line(m: dict) -> str:
    return (
        f"{m['pair']} (spot): {fmt_usd(m['last_price'])}  24h {fmt_pct(m['change_24h_pct'])}  "
        f"vol {humanize_usd(m['volume_24h_usd'])}"
    )


def _find_spot(markets: list[dict], coins: list[str]) -> list[dict]:
    selected = []
    for coin in coins:
        needle = coin.upper()
        match = next((m for m in markets if needle in (m["pair"].upper(), m["base"].upper())), None)
        if match is None:
            raise ChainqError(f"no Lighter spot market for '{coin}'")
        selected.append(match)
    return selected


@spot_app.command(name="price")
def spot_price(
    coins: Annotated[list[str], typer.Argument(help="spot tokens or pairs, e.g. ETH LIT/USDC")],
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Last price, 24h change, and volume for Lighter spot pairs."""
    out = Out(json_out, quiet, verbose, format)
    selected = _find_spot(lighter.spot_markets(), coins)
    out.emit(
        selected,
        [_spot_line(m) for m in selected],
        quiet_value="\n".join(str(m["last_price"]) for m in selected),
        verbose_lines=[
            f"{m['pair']}: market id {m['market_id']}, 24h range {fmt_usd(m['low_24h'])} - {fmt_usd(m['high_24h'])}, "
            f"24h trades {m['trades_24h']}"
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
    """Lighter spot markets by 24h volume."""
    out = Out(json_out, quiet, verbose, format)
    ranked = sorted(lighter.spot_markets(), key=lambda m: m["volume_24h_usd"], reverse=True)[:limit]
    out.emit(ranked, [_spot_line(m) for m in ranked], quiet_value="\n".join(m["pair"] for m in ranked))


@spot_app.command(name="balances")
def spot_balances(
    address: Annotated[str, typer.Argument(help="L1 account address (0x...)")],
    min_usd: Annotated[float, typer.Option("--min-usd", help="hide balances worth less than this")] = 0,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Asset balances (available, in orders, margin) with USD values for an account."""
    out = Out(json_out, quiet, verbose, format)
    addr = resolve_address(address)
    acc = lighter.account(addr)
    rows = [r for r in lighter.asset_balances(acc) if r["value_usd"] is None or r["value_usd"] >= min_usd]
    total_usd = sum(r["value_usd"] or 0 for r in rows)
    lines = [f"Lighter balances {short_addr(addr)}: ~{fmt_usd(total_usd)} across {len(rows)} assets"]
    width = max((len(r["coin"]) for r in rows), default=0)
    for r in rows:
        buckets = ", ".join(
            f"{label} {fmt_amount(r[key])}"
            for key, label in (("available", "available"), ("locked", "in orders"), ("margin", "margin"))
            if r[key]
        )
        value = f" (~{fmt_usd(r['value_usd'])})" if r["value_usd"] is not None else ""
        lines.append(f"  {r['coin']:<{width}}: {fmt_amount(r['total'])}{value}  {dim(buckets)}")
    if not rows:
        lines.append("  no balances")
    out.emit(
        {
            "address": addr,
            "account_index": acc.get("account_index"),
            "total_value_usd": total_usd,
            "balances": rows,
        },
        lines,
        quiet_value=total_usd,
        verbose_lines=[
            "margin = perp collateral held in that asset; USDC margin is the collateral shown by `lighter positions`",
            "prices: Lighter asset index prices",
        ],
    )
