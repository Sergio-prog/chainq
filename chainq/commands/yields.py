import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Annotated

import typer

from chainq.commands.aave import _reserve_row as aave_reserve_row
from chainq.commands.kamino import _reserve_row as kamino_reserve_row
from chainq.commands.morpho import _market_row as morpho_market_row
from chainq.commands.morpho import _vault_row as morpho_vault_row
from chainq.commands.pendle import _market_row as pendle_market_row
from chainq.errors import ChainqError
from chainq.fmt import dim, fmt_pct, humanize_num, humanize_usd
from chainq.networks import NETWORKS, resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import aave, aerodrome, curve, ethena, kamino, lido, morpho, pendle, sky

DEFAULT_NETWORKS = ("ethereum", "base", "solana")
KINDS = ("lending", "vault", "staking", "lp", "fixed")
SORTS = ("tvl", "apy")
ETH_FAMILY = {"eth", "weth", "steth"}
Task = tuple[str, Callable[[], list[dict]]]
TaskResult = tuple[list[dict] | None, str | None]
MARKET_WIDTH_LIMIT = 48


def _row(
    protocol: str,
    network: str,
    market: str,
    symbol: str,
    apy_pct: float | None,
    apy_reward_pct: float | None,
    kind: str,
    tvl_usd: float | None,
) -> dict:
    return {
        "protocol": protocol,
        "network": network,
        "market": market,
        "symbol": symbol.lower(),
        "apy_pct": apy_pct,
        "apy_reward_pct": apy_reward_pct,
        "type": kind,
        "tvl_usd": tvl_usd,
        "source": protocol,
    }


def _aave_rows(network: str) -> list[dict]:
    rows = []
    for market in aave.markets(NETWORKS[network].chain_id):
        for reserve in market.get("reserves") or []:
            if reserve.get("isPaused"):
                continue
            mapped = aave_reserve_row(market, reserve)
            rows.append(
                _row(
                    "aave",
                    network,
                    f"{mapped['symbol']} [{mapped['market']}]",
                    mapped["symbol"] or "",
                    mapped["supply_apy_pct"],
                    None,
                    "lending",
                    mapped["supplied_usd"],
                )
            )
    return rows


def _kamino_rows() -> list[dict]:
    rows = []
    for market in kamino.market_configs():
        for reserve in kamino.reserve_metrics(market["lendingMarket"]):
            mapped = kamino_reserve_row(market, reserve)
            if mapped is None:
                continue
            rows.append(
                _row(
                    "kamino",
                    "solana",
                    f"{mapped['symbol']} [{mapped['market']}]",
                    mapped["symbol"],
                    mapped["supply_apy_pct"],
                    None,
                    "lending",
                    mapped["supplied_usd"],
                )
            )
    return rows


def _morpho_market_rows(network: str) -> list[dict]:
    rows = []
    for market in morpho.markets(NETWORKS[network].chain_id):
        mapped = morpho_market_row(market)
        rows.append(
            _row(
                "morpho",
                network,
                f"{mapped['collateral']}/{mapped['loan']}",
                mapped["loan"] or "",
                mapped["supply_apy_pct"],
                None,
                "lending",
                mapped["supplied_usd"],
            )
        )
    return rows


def _morpho_vault_rows(network: str) -> list[dict]:
    rows = []
    for vault in morpho.vaults(NETWORKS[network].chain_id):
        mapped = morpho_vault_row(vault)
        rows.append(
            _row(
                "morpho",
                network,
                mapped["name"] or mapped["symbol"] or "vault",
                mapped["asset"] or "",
                mapped["net_apy_pct"],
                None,
                "vault",
                mapped["tvl_usd"],
            )
        )
    return rows


def _pendle_rows(network: str) -> list[dict]:
    rows = []
    for market in pendle.active_markets(NETWORKS[network].chain_id):
        mapped = pendle_market_row(market)
        rows.append(
            _row(
                "pendle",
                network,
                mapped["name"] or "market",
                mapped["name"] or "",
                mapped["implied_apy_pct"],
                None,
                "fixed",
                mapped["liquidity_usd"],
            )
        )
    return rows


def _curve_rows(network: str) -> list[dict]:
    return [
        _row(
            "curve",
            network,
            pool["name"] or pool["symbol"] or "pool",
            "/".join(coin for coin in pool["coins"] if coin),
            pool["apy_base_pct"],
            pool["apy_crv_min_pct"],
            "lp",
            pool["tvl_usd"],
        )
        for pool in curve.pools(network)
    ]


def _aerodrome_rows() -> list[dict]:
    return [
        _row(
            "aerodrome",
            "base",
            pool["symbol"],
            pool["symbol"],
            pool["apy_pct"],
            pool["apy_reward_pct"],
            "lp",
            pool["tvl_usd"],
        )
        for pool in aerodrome.top_pools(aerodrome.PROJECT_ALIASES["all"], 100)
    ]


def _sky_rows() -> list[dict]:
    data = sky.savings()
    return [
        _row("sky", "ethereum", "sUSDS", "usds", data["ssr_apy_pct"], None, "staking", data["susds_deposits_usds"]),
        _row("sky", "ethereum", "DAI Savings Rate", "dai", data["dsr_apy_pct"], None, "staking", None),
    ]


def _ethena_rows() -> list[dict]:
    data = ethena.yields()
    return [_row("ethena", "ethereum", "sUSDe", "usde", data["susde_apy_pct"], None, "staking", None)]


def _lido_rows() -> list[dict]:
    data = lido.apr()
    return [_row("lido", "ethereum", "stETH", "steth", data["steth_apr_pct"], None, "staking", None)]


def _run_task(label: str, load: Callable[[], list[dict]]) -> TaskResult:
    try:
        return load(), None
    except Exception as exc:
        return None, f"{label}: {exc}"


def _merge_results(results: list[TaskResult]) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    errors: list[str] = []
    for result_rows, error in results:
        if error:
            errors.append(error)
        elif result_rows is not None:
            rows.extend(result_rows)
    return rows, errors


def _asset_matches(row: dict, asset: str) -> bool:
    query = asset.strip().lower()
    tokens = set(re.findall(r"[a-z0-9]+", f"{row['symbol']} {row['market']}".lower()))
    if query == "eth":
        return bool(tokens & ETH_FAMILY)
    return query in tokens


def _filter_rows(
    rows: list[dict],
    asset: str | None,
    kind: str | None,
    min_tvl: float,
    sort: str,
    limit: int,
) -> list[dict]:
    if asset:
        rows = [row for row in rows if _asset_matches(row, asset)]
    if kind:
        rows = [row for row in rows if row["type"] == kind]
    rows = [row for row in rows if row["apy_pct"] is not None and (row["tvl_usd"] or 0) >= min_tvl]
    sort_key = "tvl_usd" if sort == "tvl" else "apy_pct"
    return sorted(rows, key=lambda row: row[sort_key] or 0, reverse=True)[:limit]


def _fit(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    return value[: width - 1] + "…"


def _yield_lines(rows: list[dict]) -> list[str]:
    apys = [f"{row['apy_pct']:.2f}%" for row in rows]
    kinds = [row["type"] for row in rows]
    markets = [f"{row['protocol']} {row['market']}" for row in rows]
    networks = [f"({row['network']})" for row in rows]
    tvls = [f"${humanize_num(row['tvl_usd'])}" if row["tvl_usd"] is not None else "n/a" for row in rows]
    apy_width = max(map(len, apys))
    kind_width = max(map(len, kinds))
    market_width = min(max(map(len, markets)), MARKET_WIDTH_LIMIT)
    network_width = max(map(len, networks))
    tvl_width = max(len(value) for value in tvls)
    lines = []
    for row, apy, kind, market, network, tvl in zip(rows, apys, kinds, markets, networks, tvls, strict=True):
        apy_cell = " " * (apy_width - len(apy)) + fmt_pct(row["apy_pct"], signed=False)
        kind_cell = dim(kind.ljust(kind_width))
        market_cell = _fit(market, market_width).ljust(market_width)
        network_cell = dim(network.ljust(network_width))
        tvl_value = humanize_usd(row["tvl_usd"]) if row["tvl_usd"] is not None else tvl
        tvl_cell = " " * (tvl_width - len(tvl)) + tvl_value
        lines.append(f"{apy_cell}  {kind_cell}  {market_cell}  {network_cell}  {dim('tvl')} {tvl_cell}")
    return lines


def _tasks(networks: list[str]) -> list[Task]:
    tasks: list[Task] = []
    for network in networks:
        net = NETWORKS[network]
        if net.kind == "solana":
            tasks.append(("kamino solana", _kamino_rows))
            continue
        tasks.extend(
            [
                (f"aave {network}", lambda network=network: _aave_rows(network)),
                (f"morpho markets {network}", lambda network=network: _morpho_market_rows(network)),
                (f"morpho vaults {network}", lambda network=network: _morpho_vault_rows(network)),
                (f"pendle {network}", lambda network=network: _pendle_rows(network)),
            ]
        )
        if network in curve.CHAIN_IDS:
            tasks.append((f"curve {network}", lambda network=network: _curve_rows(network)))
        if network == "base":
            tasks.append(("aerodrome base", _aerodrome_rows))
    tasks.extend([("sky ethereum", _sky_rows), ("ethena ethereum", _ethena_rows), ("lido ethereum", _lido_rows)])
    return tasks


def yields(
    asset: Annotated[str | None, typer.Option("--asset", "-a", help="filter by asset symbol or market name")] = None,
    networks: Annotated[
        list[str] | None, typer.Option("--network", "-n", help="network(s); default: ethereum, base, solana")
    ] = None,
    kind: Annotated[str | None, typer.Option("--type", help="lending | vault | staking | lp | fixed")] = None,
    min_tvl: Annotated[float, typer.Option("--min-tvl", help="minimum TVL in USD")] = 1_000_000,
    sort: Annotated[str, typer.Option("--sort", "-s", help="tvl | apy")] = "tvl",
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Compare yield opportunities across protocols and networks."""
    out = Out(json_out, quiet, verbose, format)
    if kind and kind not in KINDS:
        raise ChainqError(f"unknown yield type '{kind}' (use: {' | '.join(KINDS)})")
    if sort not in SORTS:
        raise ChainqError(f"unknown yield sort '{sort}' (use: {' | '.join(SORTS)})")
    if networks and any(network.lower() == "all" for network in networks):
        raise ChainqError("network 'all' is not supported; pass -n once per network")
    resolved = list(dict.fromkeys(resolve_network(network).key for network in networks)) if networks else list(DEFAULT_NETWORKS)
    tasks = _tasks(resolved)
    results: list[TaskResult] = []
    with ThreadPoolExecutor(max_workers=min(16, len(tasks))) as pool:
        futures = {pool.submit(_run_task, label, load): label for label, load in tasks}
        for future in as_completed(futures):
            results.append(future.result())
    rows, errors = _merge_results(results)
    if len(errors) == len(tasks):
        raise ChainqError("all yield sources failed: " + "; ".join(errors))
    rows = _filter_rows(rows, asset, kind, min_tvl, sort, limit)
    if not rows:
        raise ChainqError("no yield opportunities matched the filters")
    lines = _yield_lines(rows)
    out.emit(rows, lines, quiet_value=rows[0]["apy_pct"], verbose_lines=errors)
