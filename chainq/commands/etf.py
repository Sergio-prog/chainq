from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import RED, dim, green, humanize_num, paint
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import theblock

META_FIELDS = ("date", "net_flow_usd")


def _flow_text(value: float) -> str:
    return f"{'+' if value >= 0 else '-'}${humanize_num(abs(value))}"


def _flow_cell(value: float, width: int = 0) -> str:
    text = _flow_text(value).rjust(width)
    return green(text) if value >= 0 else paint(text, RED)


def _issuers(row: dict) -> dict[str, float]:
    return {k: v for k, v in row.items() if k not in META_FIELDS}


def etf(
    asset: Annotated[str, typer.Argument(help="ETF underlying: btc | eth")] = "btc",
    days: Annotated[int, typer.Option("--days", "-d", help="number of recent trading days")] = 14,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Daily spot crypto ETF net inflows/outflows (US), per issuer and total, by trading day."""
    out = Out(json_out, quiet, verbose, format)
    symbol = asset.strip().upper()
    if symbol not in theblock.ASSETS:
        raise ChainqError(f"no ETF flow data for '{asset}' (supported: {', '.join(a.lower() for a in theblock.ASSETS)})")
    rows = theblock.flow_history(symbol)[:days]
    if not rows:
        raise ChainqError(f"no ETF flow data returned for {symbol}")
    source_url = theblock.SITE[symbol]
    data = {
        "asset": symbol,
        "unit": "usd",
        "source": theblock.SOURCE,
        "source_url": source_url,
        "as_of": rows[0]["date"],
        "flows": rows,
    }
    flow_width = max(len(_flow_text(row["net_flow_usd"])) for row in rows)
    lines = [f"{symbol} spot ETF net flows {dim(f'(US, last {len(rows)} trading days, {theblock.SOURCE})')}"]
    for row in rows:
        issuers = _issuers(row)
        top = max(issuers.items(), key=lambda kv: abs(kv[1])) if issuers else None
        lead = f"  {dim('top')} {top[0]} {_flow_cell(top[1])}" if top else ""
        lines.append(f"  {dim(row['date'])}  {_flow_cell(row['net_flow_usd'], flow_width)}{lead}")
    latest = rows[0]
    latest_issuers = sorted(_issuers(latest).items(), key=lambda kv: abs(kv[1]), reverse=True)
    out.emit(
        data,
        lines,
        quiet_value=latest["net_flow_usd"],
        verbose_lines=[
            f"{latest['date']} by issuer: "
            + ", ".join(f"{name} {_flow_text(value)}" for name, value in latest_issuers),
            f"source: {theblock.SOURCE} — {source_url}",
        ],
    )
