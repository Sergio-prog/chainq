from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_amount, fmt_pct, fmt_usd, humanize_usd, short_addr
from chainq.output import JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import hyperliquid
from chainq.rpc import resolve_address

app = typer.Typer(no_args_is_help=True, help="Hyperliquid public market data (perps).")


def _market_line(m: dict) -> str:
    return (
        f"{m['coin']}-PERP: mark {fmt_usd(m['mark_price'])}  24h {fmt_pct(m['change_24h_pct'])}  "
        f"vol {humanize_usd(m['volume_24h_usd'])}  OI {humanize_usd(m['open_interest_usd'])}  "
        f"funding {m['funding_hourly_pct']:+.4f}%/h ({m['funding_apr_pct']:+.1f}% APR)"
    )


def _find(markets: list[dict], coins: list[str]) -> list[dict]:
    by_coin = {m["coin"].upper(): m for m in markets}
    selected = []
    for coin in coins:
        m = by_coin.get(coin.upper())
        if m is None:
            raise ChainqError(f"no Hyperliquid perp market for '{coin}'")
        selected.append(m)
    return selected


@app.command()
def price(
    coins: Annotated[list[str], typer.Argument(help="perp coins, e.g. BTC ETH HYPE")],
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
):
    """Mark price, 24h change, volume, OI, and funding for perp markets."""
    out = Out(json_out, quiet, verbose)
    selected = _find(hyperliquid.perp_markets(), coins)
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
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
):
    """Top perp markets ranked by volume, OI, funding, or 24h change."""
    out = Out(json_out, quiet, verbose)
    keys = {
        "volume": lambda m: m["volume_24h_usd"],
        "oi": lambda m: m["open_interest_usd"],
        "funding": lambda m: abs(m["funding_hourly_pct"]),
        "change": lambda m: abs(m["change_24h_pct"] or 0),
    }
    if sort not in keys:
        raise ChainqError(f"unknown sort '{sort}' (use: {', '.join(keys)})")
    ranked = sorted(hyperliquid.perp_markets(), key=keys[sort], reverse=True)[:limit]
    out.emit(
        ranked,
        [_market_line(m) for m in ranked],
        quiet_value="\n".join(m["coin"] for m in ranked),
    )


@app.command()
def funding(
    coins: Annotated[list[str] | None, typer.Argument(help="perp coins; omit for top by |rate|")] = None,
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
):
    """Current hourly funding rates and annualized APR."""
    out = Out(json_out, quiet, verbose)
    all_markets = hyperliquid.perp_markets()
    if coins:
        selected = _find(all_markets, coins)
    else:
        selected = sorted(all_markets, key=lambda m: abs(m["funding_hourly_pct"]), reverse=True)[:limit]
    lines = [
        f"{m['coin']}-PERP funding: {m['funding_hourly_pct']:+.4f}%/h ({m['funding_apr_pct']:+.1f}% APR)  "
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
):
    """Open perp positions and margin summary for an account."""
    out = Out(json_out, quiet, verbose)
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
            f"value {fmt_usd(float(p.get('positionValue') or 0))}, uPnL {fmt_usd(pnl)} ({roe:+.1f}%), "
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
