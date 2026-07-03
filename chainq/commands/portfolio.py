from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_amount, fmt_usd, short_addr
from chainq.networks import NETWORKS, resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import coingecko
from chainq.rpc import connect, erc20, resolve_address
from chainq.tokens import TOKENS


def _scan_network(net_key: str, address: str) -> list[dict]:
    net = NETWORKS[net_key]
    client = connect(net)
    assets = []
    wei = client.w3.eth.get_balance(address)
    if wei:
        assets.append(
            {
                "network": net.key,
                "symbol": net.native_symbol,
                "token_address": None,
                "amount": str(Decimal(wei) / Decimal(10**18)),
                "coingecko_id": net.native_coingecko_id,
            }
        )
    for symbol, token_address in TOKENS.get(net.key, {}).items():
        contract = erc20(client, token_address)
        raw = contract.functions.balanceOf(address).call()
        if not raw:
            continue
        decimals = contract.functions.decimals().call()
        assets.append(
            {
                "network": net.key,
                "symbol": contract.functions.symbol().call(),
                "token_address": token_address,
                "amount": str(Decimal(raw) / Decimal(10**decimals)),
                "coingecko_id": coingecko.SYMBOL_TO_ID.get(symbol),
            }
        )
    return assets


def _priced(assets: list[dict]) -> list[dict]:
    ids = sorted({a["coingecko_id"] for a in assets if a["coingecko_id"]})
    prices = {}
    if ids:
        try:
            prices = coingecko.simple_price(ids)
        except Exception:
            prices = {}
    for asset in assets:
        price = (prices.get(asset.pop("coingecko_id")) or {}).get("usd")
        asset["price_usd"] = price
        asset["value_usd"] = float(asset["amount"]) * price if price is not None else None
    return assets


def portfolio(
    address: Annotated[str, typer.Argument(help="wallet address or ENS name")],
    networks: Annotated[
        list[str] | None, typer.Option("--network", "-n", help="network(s) to scan; default: all")
    ] = None,
    min_usd: Annotated[float, typer.Option("--min-usd", help="hide assets worth less than this")] = 0.01,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Sweep native + known tokens across networks with USD totals."""
    out = Out(json_out, quiet, verbose, format)
    addr = resolve_address(address)
    keys = [resolve_network(n).key for n in networks] if networks else list(NETWORKS)
    assets: list[dict] = []
    unreachable: list[str] = []
    with ThreadPoolExecutor(max_workers=min(12, len(keys))) as pool:
        futures = {pool.submit(_scan_network, key, addr): key for key in keys}
        for future in as_completed(futures):
            try:
                assets.extend(future.result())
            except Exception:
                unreachable.append(futures[future])
    assets = _priced(assets)
    assets = [a for a in assets if a["value_usd"] is None or a["value_usd"] >= min_usd]
    assets.sort(key=lambda a: (a["value_usd"] is None, -(a["value_usd"] or 0)))
    if not assets and unreachable:
        raise ChainqError(f"no assets found; unreachable networks: {', '.join(sorted(unreachable))}")
    total = sum(a["value_usd"] or 0 for a in assets)
    data = {
        "address": addr,
        "input": address,
        "networks_scanned": len(keys) - len(unreachable),
        "unreachable": sorted(unreachable),
        "total_usd": total,
        "assets": assets,
    }
    label = f"{address} ({short_addr(addr)})" if address != addr else short_addr(addr)
    lines = [f"{label}: ≈ {fmt_usd(total)} across {len({a['network'] for a in assets})} network(s)"]
    lines += [
        f"  {a['network']}: {fmt_amount(a['amount'])} {a['symbol']}"
        + (f" (~{fmt_usd(a['value_usd'])})" if a["value_usd"] is not None else "")
        for a in assets
    ]
    if unreachable:
        lines.append(f"  (unreachable: {', '.join(sorted(unreachable))})")
    out.emit(
        data,
        lines,
        quiet_value=total,
        verbose_lines=[
            f"scanned {len(keys)} network(s), tokens from the built-in registry only",
            f"address: {addr}",
        ],
    )
