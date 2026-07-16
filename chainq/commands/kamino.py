import math
from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_pct, humanize_usd
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import kamino

app = typer.Typer(no_args_is_help=True, help="Kamino lending markets on Solana.")

SORT_KEYS = {
    "supplied": lambda row: row["supplied_usd"],
    "supply-apy": lambda row: row["supply_apy_pct"],
    "borrow-apy": lambda row: row["borrow_apy_pct"],
    "utilization": lambda row: row["utilization_pct"] or 0,
}


def _number(value: object) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError
    number = float(value)
    if not math.isfinite(number):
        raise ValueError
    return number


def _reserve_row(market: dict, reserve: dict) -> dict | None:
    if not isinstance(market, dict) or not isinstance(reserve, dict):
        return None
    try:
        market_name = market.get("name")
        market_address = market.get("lendingMarket")
        symbol = reserve.get("liquidityToken")
        mint = reserve.get("liquidityTokenMint")
        reserve_address = reserve.get("reserve")
        if not all(isinstance(value, str) and value for value in (market_name, market_address, symbol, mint, reserve_address)):
            return None
        supplied_usd = _number(reserve.get("totalSupplyUsd"))
        borrowed_usd = _number(reserve.get("totalBorrowUsd"))
        return {
            "market": market_name,
            "market_address": market_address,
            "symbol": symbol,
            "mint": mint,
            "supply_apy_pct": _number(reserve.get("supplyApy")) * 100,
            "borrow_apy_pct": _number(reserve.get("borrowApy")) * 100,
            "supplied_usd": supplied_usd,
            "borrowed_usd": borrowed_usd,
            "utilization_pct": borrowed_usd / supplied_usd * 100 if supplied_usd else None,
            "max_ltv_pct": _number(reserve.get("maxLtv")) * 100,
            "reserve_address": reserve_address,
        }
    except (TypeError, ValueError, OverflowError):
        return None


def _collect_rows(markets: list[dict], reserves: list[list[dict]]) -> tuple[list[dict], int]:
    rows: list[dict] = []
    skipped = 0
    for market, market_reserves in zip(markets, reserves, strict=True):
        for reserve in market_reserves:
            row = _reserve_row(market, reserve)
            if row is None:
                skipped += 1
            else:
                rows.append(row)
    return rows, skipped


def _filter_rows(rows: list[dict], coin: str | None) -> list[dict]:
    if not coin:
        return rows
    query = coin.lower()
    return [row for row in rows if row["symbol"].lower() == query or row["mint"].lower() == query]


def _sort_rows(rows: list[dict], sort: str) -> list[dict]:
    return sorted(rows, key=SORT_KEYS[sort], reverse=True)


def _row_line(row: dict) -> str:
    utilization = fmt_pct(row["utilization_pct"], signed=False) if row["utilization_pct"] is not None else "n/a"
    return (
        f"{row['symbol']} [{row['market']}]: supply {fmt_pct(row['supply_apy_pct'], signed=False)}  "
        f"borrow {fmt_pct(row['borrow_apy_pct'], signed=False)}  supplied {humanize_usd(row['supplied_usd'])}  "
        f"util {utilization}"
    )


def _selected_markets(markets: list[dict], market: str | None) -> list[dict]:
    if not market:
        return markets
    query = market.lower()
    return [
        config
        for config in markets
        if config["lendingMarket"].lower() == query or query in str(config.get("name") or "").lower()
    ]


@app.command()
def markets(
    coin: Annotated[str | None, typer.Option("--coin", "-c", help="filter by token symbol or mint")] = None,
    market: Annotated[str | None, typer.Option("--market", "-m", help="filter by market name or address")] = None,
    sort: Annotated[str, typer.Option("--sort", "-s", help="supplied | supply-apy | borrow-apy | utilization")] = "supplied",
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Kamino lending reserves: supply/borrow APY, size, utilization."""
    out = Out(json_out, quiet, verbose, format)
    if sort not in SORT_KEYS:
        raise ChainqError(f"unknown sort '{sort}' (use: {', '.join(SORT_KEYS)})")
    configs = kamino.market_configs()
    if not configs:
        raise ChainqError("no Kamino lending markets found")
    selected = _selected_markets(configs, market)
    if not selected:
        raise ChainqError(f"no Kamino market matching '{market}'")
    reserve_sets = [kamino.reserve_metrics(config["lendingMarket"]) for config in selected]
    all_rows, skipped = _collect_rows(selected, reserve_sets)
    total = sum(row["supplied_usd"] for row in all_rows)
    rows = _sort_rows(_filter_rows(all_rows, coin), sort)
    if coin and not rows:
        raise ChainqError(f"no Kamino reserve for '{coin}' on Solana")
    if not coin:
        rows = rows[:limit]
    header = (
        f"Kamino on Solana: {humanize_usd(total)} total supplied, "
        f"{len(selected)} market{'s' if len(selected) != 1 else ''}"
    )
    out.emit(
        {"network": "solana", "total_supplied_usd": total, "reserves": rows},
        [header, *(_row_line(row) for row in rows)],
        quiet_value="\n".join(row["symbol"] for row in rows),
        verbose_lines=[
            *(
                f"{row['symbol']} [{row['market']}]: mint {row['mint']}, reserve {row['reserve_address']}, "
                f"market {row['market_address']}, max LTV {fmt_pct(row['max_ltv_pct'], signed=False)}, "
                "source: api.kamino.finance"
                for row in rows
            ),
            f"skipped malformed reserves: {skipped}",
        ],
    )
