from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import bold, dim, humanize_num
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import buybacks as provider


def _rows(programs: list[dict]) -> list[dict]:
    rows = []
    for prog in programs:
        for period in prog["periods"]:
            rows.append(
                {
                    "program": prog["program"],
                    "asset": prog["asset"],
                    "period": period["period"],
                    "tokens": period["tokens"],
                    "usd": period["usd"],
                    "avg_price_usd": period["avg_price_usd"],
                    "cadence": prog["cadence"],
                    "provenance": prog["provenance"],
                    "source": prog["source"],
                    "source_url": prog["source_url"],
                }
            )
    return rows


def _money(value: float | None) -> str:
    return f"${humanize_num(value)}" if value else ""


def _lines(prog: dict) -> list[str]:
    periods, asset = prog["periods"], prog["asset"]
    cumulative_tokens, cumulative_usd = prog["cumulative_tokens"], prog["cumulative_usd"]
    cum_avg = cumulative_usd / cumulative_tokens if cumulative_usd and cumulative_tokens else None
    averages = [p["avg_price_usd"] for p in periods if p["avg_price_usd"]] + ([cum_avg] if cum_avg else [])
    decimals = 2 if averages and min(averages) >= 1 else 4

    def price(value: float | None) -> str:
        return f"${value:,.{decimals}f}" if value else ""

    body = [
        (p["period"], humanize_num(p["tokens"]), _money(p["usd"]), price(p["avg_price_usd"])) for p in periods
    ]
    total = ("total", humanize_num(cumulative_tokens), _money(cumulative_usd), price(cum_avg))
    head = ("period", asset, "cost", "avg")
    grid = [head, *body, total]
    keep = [0, 1] + [i for i in (2, 3) if any(row[i] for row in grid[1:])]
    widths = [max(len(row[i]) for row in grid) for i in range(4)]

    def render(row: tuple, paint) -> str:
        cells = [row[i].rjust(widths[i]) if i else row[i].ljust(widths[i]) for i in keep]
        return "  " + paint("  ".join(cells).rstrip())

    window = f"  {dim(f'last {prog["window_days"]}d')}" if prog["window_days"] else ""
    lines = [
        f"{bold(asset)} buybacks  {dim(f'{prog["cadence"]} · {prog["provenance"]} · {prog["source"]}')}{window}",
        render(head, dim),
    ]
    lines.extend(render(row, lambda text: text) for row in body)
    lines.append(render(total, bold))
    lines.append(f"  {dim(prog['source_url'])}")
    return lines


def buybacks(
    programs: Annotated[
        list[str],
        typer.Argument(help="programs to report: hype, sky, uni, zro, lit (e.g. `chainq buybacks hype uni`)"),
    ],
    days: Annotated[int, typer.Option("--days", "-d", help="lookback window for daily programs")] = 14,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Token buybacks by their real reporting period, with source and provenance."""
    out = Out(json_out, quiet, verbose, format)
    names = list(dict.fromkeys(p.lower() for p in programs))
    unknown = [n for n in names if n not in provider.PROGRAMS]
    if unknown:
        raise ChainqError(f"unknown buyback program(s): {', '.join(unknown)} (use: {' | '.join(provider.PROGRAMS)})")
    collected: dict[str, dict] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(4, len(names))) as pool:
        futures = {pool.submit(provider.PROGRAMS[name], days): name for name in names}
        for future in as_completed(futures):
            name = futures[future]
            try:
                collected[name] = future.result()
            except Exception as exc:
                errors.append(f"{name}: {exc}")
    ordered = [collected[name] for name in names if name in collected]
    if not ordered:
        if len(names) == 1 and errors:
            raise ChainqError(errors[0].split(": ", 1)[1])
        raise ChainqError("all buyback sources failed: " + "; ".join(errors))
    text: list[str] = []
    for prog in ordered:
        if text:
            text.append("")
        text.extend(_lines(prog))
    out.emit(
        _rows(ordered),
        text,
        quiet_value="\n".join(f"{p['program']} {p['cumulative_tokens']}" for p in ordered),
        verbose_lines=[f"{p['program']}: {p['note']} [{p['provenance']}]" for p in ordered] + errors,
    )
