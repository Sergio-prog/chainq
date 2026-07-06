from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from typing import Annotated

import typer

from chainq import solana
from chainq.errors import ChainqError
from chainq.fmt import fmt_amount, fmt_usd, short_addr
from chainq.networks import NETWORKS, resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import coingecko, hyperliquid
from chainq.rpc import connect, erc20, resolve_address, sweep_balances
from chainq.tokens import MINT_TO_SYMBOL, TOKENS


def _scan_evm_legacy(client, net, address: str) -> list[dict]:
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


def _scan_evm(net_key: str, address: str) -> list[dict]:
    net = NETWORKS[net_key]
    client = connect(net)
    try:
        wei, rows = sweep_balances(client, address, TOKENS.get(net.key, {}))
    except Exception:
        return _scan_evm_legacy(client, net, address)
    assets = []
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
    for row in rows:
        assets.append(
            {
                "network": net.key,
                "symbol": row["symbol"],
                "token_address": row["token_address"],
                "amount": str(Decimal(row["raw_amount"]) / Decimal(10 ** row["decimals"])),
                "coingecko_id": coingecko.SYMBOL_TO_ID.get(row["registry_symbol"]),
            }
        )
    return assets


def _scan_solana(address: str) -> list[dict]:
    assets = []
    lamports = solana.get_balance(address)
    if lamports:
        assets.append(
            {
                "network": "solana",
                "symbol": "SOL",
                "token_address": None,
                "amount": str(solana.lamports_to_sol(lamports)),
                "coingecko_id": "solana",
            }
        )
    for account in solana.token_accounts(address):
        if not account["raw_amount"]:
            continue
        registry_symbol = MINT_TO_SYMBOL.get(account["mint"])
        assets.append(
            {
                "network": "solana",
                "symbol": registry_symbol.upper() if registry_symbol else short_addr(account["mint"]),
                "token_address": account["mint"],
                "amount": account["amount"],
                "coingecko_id": coingecko.SYMBOL_TO_ID.get(registry_symbol),
            }
        )
    return assets


def _scan_network(net_key: str, address: str) -> list[dict]:
    if NETWORKS[net_key].kind == "solana":
        return _scan_solana(address)
    return _scan_evm(net_key, address)


def _scan_hyperliquid(address: str) -> list[dict]:
    assets: list[dict] = []
    try:
        state = hyperliquid.clearinghouse_state(address)
        equity = float((state.get("marginSummary") or {}).get("accountValue") or 0)
        if equity:
            assets.append(
                {
                    "network": "hyperliquid",
                    "symbol": "perp equity (USDC)",
                    "token_address": None,
                    "amount": str(equity),
                    "price_usd": 1.0,
                    "value_usd": equity,
                }
            )
    except Exception:
        pass
    try:
        balances = hyperliquid.spot_balances(address)
    except Exception:
        return assets
    if not balances:
        return assets
    prices = {"USDC": 1.0}
    for m in hyperliquid.spot_markets():
        price = m["mid_price"] or m["mark_price"]
        if m["base"] and price:
            prices[m["base"]] = price
    for b in balances:
        total = float(b.get("total") or 0)
        if not total:
            continue
        price = prices.get(b.get("coin"))
        assets.append(
            {
                "network": "hyperliquid",
                "symbol": b.get("coin"),
                "token_address": None,
                "amount": str(total),
                "price_usd": price,
                "value_usd": total * price if price is not None else None,
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


def _resolve_scan_target(address: str, networks: list[str] | None) -> tuple[str, list[str]]:
    value = address.strip()
    if solana.looks_like_solana(value):
        kind, addr = "solana", solana.resolve_solana_address(value)
    else:
        kind, addr = "evm", resolve_address(value)
    if networks:
        requested = [resolve_network(n) for n in networks]
        mismatched = [n.key for n in requested if n.kind != kind]
        if mismatched:
            raise ChainqError(
                f"{', '.join(mismatched)} cannot hold this address "
                f"({'base58 Solana pubkey' if kind == 'solana' else '0x EVM address'})"
            )
        return addr, [n.key for n in requested]
    return addr, [key for key, net in NETWORKS.items() if net.kind == kind]


def portfolio(
    address: Annotated[str, typer.Argument(help="wallet address (0x or Solana base58), ENS, or .sol name")],
    networks: Annotated[
        list[str] | None, typer.Option("--network", "-n", help="network(s) to scan; default: all")
    ] = None,
    min_usd: Annotated[float, typer.Option("--min-usd", help="hide assets worth less than this")] = 0.01,
    hide_unpriced: Annotated[
        bool, typer.Option("--hide-unpriced", help="drop assets with no known USD price")
    ] = False,
    defi: Annotated[
        bool, typer.Option("--defi", help="also fold in Hyperliquid perp equity and spot balances")
    ] = False,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Sweep native + known tokens across networks with USD totals."""
    out = Out(json_out, quiet, verbose, format)
    addr, keys = _resolve_scan_target(address, networks)
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
    if defi and addr.startswith("0x"):
        assets.extend(_scan_hyperliquid(addr))
    kept = []
    hidden = 0
    for a in assets:
        if a["value_usd"] is None:
            if hide_unpriced:
                hidden += 1
                continue
        elif a["value_usd"] < min_usd:
            hidden += 1
            continue
        kept.append(a)
    assets = kept
    assets.sort(key=lambda a: (a["value_usd"] is None, -(a["value_usd"] or 0)))
    if not assets and unreachable:
        raise ChainqError(f"no assets found; unreachable networks: {', '.join(sorted(unreachable))}")
    total = sum(a["value_usd"] or 0 for a in assets)
    data = {
        "address": addr,
        "input": address,
        "networks_scanned": len(keys) - len(unreachable),
        "unreachable": sorted(unreachable),
        "hidden_assets": hidden,
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
    if hidden:
        lines.append(f"  ({hidden} asset(s) below {fmt_usd(min_usd)}{' or unpriced' if hide_unpriced else ''} hidden)")
    if unreachable:
        lines.append(f"  (unreachable: {', '.join(sorted(unreachable))})")
    out.emit(
        data,
        lines,
        quiet_value=total,
        verbose_lines=[
            f"scanned {len(keys)} network(s), registry tokens" + (" + Hyperliquid" if defi else ""),
            f"address: {addr}",
        ],
    )
