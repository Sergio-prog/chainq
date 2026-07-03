from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_pct, fmt_usd, humanize_usd
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import defillama

MECHANISMS = ("fiat-backed", "crypto-backed", "algorithmic")


def _change_pct(current: float | None, previous: float | None) -> float | None:
    if not current or not previous:
        return None
    return (current / previous - 1) * 100


def stables(
    coin: Annotated[str | None, typer.Argument(help="filter by symbol or name, e.g. usde")] = None,
    mechanism: Annotated[
        str | None, typer.Option("--mechanism", "-m", help="fiat-backed | crypto-backed | algorithmic")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Stablecoins ranked by market cap: peg price, supply changes, mechanism."""
    out = Out(json_out, quiet, verbose, format)
    if mechanism is not None and mechanism not in MECHANISMS:
        raise ChainqError(f"unknown mechanism '{mechanism}' (use: {', '.join(MECHANISMS)})")
    rows = [dict(s) for s in defillama.stablecoins() if s["mcap_usd"]]
    total_mcap = sum(r["mcap_usd"] for r in rows)
    if coin:
        needle = coin.strip().lower()
        rows = [r for r in rows if needle in (r["symbol"] or "").lower() or needle in (r["name"] or "").lower()]
        if not rows:
            raise ChainqError(f"no stablecoin matching '{coin}'")
    if mechanism:
        rows = [r for r in rows if r["mechanism"] == mechanism]
        if not rows:
            raise ChainqError(f"no {mechanism} stablecoin matching the filter")
    rows.sort(key=lambda r: r["mcap_usd"], reverse=True)
    rows = rows[:limit]
    for r in rows:
        r["change_7d_pct"] = _change_pct(r["mcap_usd"], r.pop("mcap_prev_week_usd"))
        r["change_30d_pct"] = _change_pct(r["mcap_usd"], r.pop("mcap_prev_month_usd"))
        r.pop("mcap_prev_day_usd")
    data = {"total_mcap_usd": total_mcap, "tracked": len(defillama.stablecoins()), "stablecoins": rows}
    lines = [f"Total stablecoin mcap: {humanize_usd(total_mcap)} ({data['tracked']} tracked)"]
    lines += [
        f"{i}. {r['symbol']} ({r['name']}): {humanize_usd(r['mcap_usd'])}"
        + (f"  price {fmt_usd(r['price_usd'])}" if r["price_usd"] is not None else "")
        + f"  7d {fmt_pct(r['change_7d_pct'])}  [{r['mechanism'] or 'n/a'}]"
        for i, r in enumerate(rows, 1)
    ]
    out.emit(
        data,
        lines,
        quiet_value=total_mcap,
        verbose_lines=[
            f"{r['symbol']}: 30d {fmt_pct(r['change_30d_pct'])}, peg {r['peg_type']}, gecko id {r['gecko_id'] or 'n/a'}"
            for r in rows
        ],
    )
