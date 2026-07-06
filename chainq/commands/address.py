from decimal import Decimal
from typing import Annotated

import typer
from web3 import Web3

from chainq import solana
from chainq.fmt import fmt_amount, fmt_usd, short_addr
from chainq.networks import resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import coingecko
from chainq.rpc import (
    connect,
    decode_string,
    decode_uint,
    encode_erc20,
    multicall,
    resolve_address,
    sweep_balances,
)
from chainq.tokens import MINT_TO_SYMBOL, TOKENS

NetworkOpt = Annotated[str, typer.Option("--network", "-n", help="network key, alias, or chain id")]

EIP1967_IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
EIP1967_BEACON_SLOT = "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50"
ZEPPELINOS_IMPL_SLOT = "0x7050c9e0f4ca769c69bd3a8ef740bc37934f8e2c036e5a723fd8ee048ed3f8c3"
EIP1167_PREFIX = "363d3d373d3d3d363d73"
EIP1167_SUFFIX = "5af43d82803e903d91602b57fd5bf3"
SYSTEM_PROGRAM = "11111111111111111111111111111111"


def _slot_address(client, addr: str, slot: str) -> str | None:
    try:
        word = client.w3.eth.get_storage_at(addr, int(slot, 16))
    except Exception:
        return None
    value = int.from_bytes(word, "big")
    if not value:
        return None
    return Web3.to_checksum_address(f"0x{value & (2**160 - 1):040x}")


def _proxy_target(client, addr: str, code: bytes) -> str | None:
    code_hex = code.hex().removeprefix("0x")
    if code_hex.startswith(EIP1167_PREFIX) and code_hex.endswith(EIP1167_SUFFIX):
        return Web3.to_checksum_address(f"0x{code_hex[len(EIP1167_PREFIX):len(EIP1167_PREFIX) + 40]}")
    return (
        _slot_address(client, addr, EIP1967_IMPL_SLOT)
        or _slot_address(client, addr, EIP1967_BEACON_SLOT)
        or _slot_address(client, addr, ZEPPELINOS_IMPL_SLOT)
    )


def _erc20_profile(client, addr: str) -> dict | None:
    try:
        name, symbol, decimals, supply = multicall(
            client,
            [
                (addr, encode_erc20("name")),
                (addr, encode_erc20("symbol")),
                (addr, encode_erc20("decimals")),
                (addr, encode_erc20("totalSupply")),
            ],
        )
    except Exception:
        return None
    if symbol is None or decimals is None or supply is None:
        return None
    dec = decode_uint(decimals)
    if dec > 36:
        return None
    return {
        "name": decode_string(name) if name else None,
        "symbol": decode_string(symbol),
        "decimals": dec,
        "total_supply": str(Decimal(decode_uint(supply)) / Decimal(10**dec)),
    }


def _holdings(client, net, addr: str) -> tuple[list[dict], float | None, Decimal]:
    wei, rows = sweep_balances(client, addr, TOKENS.get(net.key, {}))
    native_amount = Decimal(wei) / Decimal(10**18)
    ids = {net.native_coingecko_id}
    for row in rows:
        cg_id = coingecko.SYMBOL_TO_ID.get(row["registry_symbol"])
        row["coingecko_id"] = cg_id
        if cg_id:
            ids.add(cg_id)
    try:
        prices = coingecko.simple_price(sorted(ids))
    except Exception:
        prices = {}
    native_price = (prices.get(net.native_coingecko_id) or {}).get("usd")
    holdings = []
    for row in rows:
        amount = Decimal(row["raw_amount"]) / Decimal(10 ** row["decimals"])
        price = (prices.get(row.pop("coingecko_id")) or {}).get("usd")
        holdings.append(
            {
                "symbol": row["symbol"],
                "token_address": row["token_address"],
                "amount": str(amount),
                "value_usd": float(amount) * price if price is not None else None,
            }
        )
    holdings.sort(key=lambda h: (h["value_usd"] is None, -(h["value_usd"] or 0)))
    return holdings, native_price, native_amount


def _evm_address(out: Out, target: str, net) -> None:
    addr = resolve_address(target)
    client = connect(net)
    code = client.w3.eth.get_code(addr)
    nonce = client.w3.eth.get_transaction_count(addr)
    holdings, native_price, native_amount = _holdings(client, net, addr)
    native_value = float(native_amount) * native_price if native_price is not None else None
    code_hex = code.hex().removeprefix("0x")
    delegated_to = Web3.to_checksum_address(f"0x{code_hex[6:46]}") if code_hex.startswith("ef0100") else None
    proxy_target = _proxy_target(client, addr, code) if code and not delegated_to else None
    erc20_info = _erc20_profile(client, addr) if code and not delegated_to else None
    ens_name = None
    if net.key == "ethereum":
        try:
            ens_name = client.w3.ens.name(addr)
        except Exception:
            ens_name = None
    kind = "eoa" if not code or delegated_to else "contract"
    data = {
        "address": addr,
        "input": target,
        "network": net.key,
        "type": kind,
        "ens_name": ens_name,
        "bytecode_bytes": len(code) or None,
        "eip7702_delegate": delegated_to,
        "proxy_implementation": proxy_target,
        "erc20": erc20_info,
        "tx_count": nonce,
        "native_amount": str(native_amount),
        "native_value_usd": native_value,
        "holdings": holdings,
        "explorer": f"{net.explorer}/address/{addr}",
    }
    what = "EOA (wallet)" if kind == "eoa" else f"contract ({len(code):,} bytes)"
    if delegated_to:
        what = f"EOA (wallet, EIP-7702 delegated → {delegated_to})"
    elif proxy_target:
        what = f"proxy contract → {proxy_target}"
    lines = [f"{short_addr(addr)} on {net.name}: {what}"]
    if ens_name:
        lines.append(f"  ENS: {ens_name}")
    if erc20_info:
        lines.append(
            f"  ERC-20: {erc20_info['name'] or erc20_info['symbol']} ({erc20_info['symbol']}), "
            f"{erc20_info['decimals']} decimals, supply {fmt_amount(erc20_info['total_supply'])}"
        )
    native_line = f"  native: {fmt_amount(native_amount)} {net.native_symbol}"
    if native_value is not None:
        native_line += f" (~{fmt_usd(native_value)})"
    lines.append(native_line + f"  outgoing txs: {nonce:,}")
    if holdings:
        shown = ", ".join(
            f"{fmt_amount(h['amount'])} {h['symbol']}"
            + (f" (~{fmt_usd(h['value_usd'])})" if h["value_usd"] is not None else "")
            for h in holdings[:5]
        )
        more = f" (+{len(holdings) - 5} more)" if len(holdings) > 5 else ""
        lines.append(f"  tokens: {shown}{more}")
    out.emit(
        data,
        lines,
        quiet_value=kind,
        verbose_lines=[f"explorer: {data['explorer']}", f"rpc: {client.url}"],
    )


def _solana_address(out: Out, target: str, net) -> None:
    addr = solana.resolve_solana_address(target)
    info = solana.account_info(addr)
    lamports = (info or {}).get("lamports") or 0
    amount = solana.lamports_to_sol(lamports)
    price = coingecko.try_price_usd("solana")
    value = float(amount) * price if price is not None else None
    owner = (info or {}).get("owner")
    executable = bool((info or {}).get("executable"))
    if info is None:
        kind = "unfunded account"
    elif executable:
        kind = "program"
    elif owner == SYSTEM_PROGRAM:
        kind = "wallet (system account)"
    else:
        kind = f"account owned by {owner}"
    accounts = [] if executable else [a for a in solana.token_accounts(addr) if a["raw_amount"]]
    totals: dict[str, Decimal] = {}
    for account in accounts:
        if account["mint"] in MINT_TO_SYMBOL:
            totals[account["mint"]] = totals.get(account["mint"], Decimal(0)) + Decimal(account["amount"])
    known = [{"mint": mint, "amount": str(total)} for mint, total in totals.items()]
    data = {
        "address": addr,
        "input": target,
        "network": net.key,
        "type": "program" if executable else ("wallet" if info else "unfunded"),
        "owner_program": owner,
        "native_amount": str(amount),
        "native_value_usd": value,
        "token_accounts": len(accounts),
        "known_tokens": [
            {"symbol": MINT_TO_SYMBOL[a["mint"]].upper(), "mint": a["mint"], "amount": a["amount"]} for a in known
        ],
        "explorer": f"{net.explorer}/account/{addr}",
    }
    lines = [f"{short_addr(addr)} on Solana: {kind}"]
    native_line = f"  native: {fmt_amount(amount)} SOL"
    if value is not None:
        native_line += f" (~{fmt_usd(value)})"
    lines.append(native_line)
    if accounts:
        shown = ", ".join(f"{fmt_amount(a['amount'])} {MINT_TO_SYMBOL[a['mint']].upper()}" for a in known[:5])
        summary = f"  token accounts: {len(accounts)}"
        if shown:
            summary += f" — {shown}"
        lines.append(summary)
    out.emit(
        data,
        lines,
        quiet_value=data["type"],
        verbose_lines=[f"owner program: {owner}", f"explorer: {data['explorer']}"],
    )


def address(
    target: Annotated[str, typer.Argument(help="address (0x or Solana base58), ENS, or .sol name")],
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Inspect an address: EOA vs contract vs program, proxies, activity, holdings."""
    out = Out(json_out, quiet, verbose, format)
    value = target.strip()
    if solana.looks_like_solana(value):
        net = resolve_network("solana")
        return _solana_address(out, value, net)
    net = resolve_network(network)
    if net.kind == "solana":
        return _solana_address(out, value, net)
    _evm_address(out, value, net)
