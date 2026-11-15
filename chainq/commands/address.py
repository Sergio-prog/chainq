from decimal import Decimal
from typing import Annotated

import typer
from web3 import Web3

from chainq import catalog, pricing, solana, tron
from chainq.commands import tron_chain
from chainq.commands.chain import _solana_symbol
from chainq.commands.portfolio import scan_solana
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
    sweep_catalog,
)

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


def _holdings(client, net, addr: str) -> tuple[list[dict], int, float | None, Decimal]:
    wei, rows = sweep_catalog(client, addr, list(catalog.tokens_for(net.key)))
    native_amount = Decimal(wei) / Decimal(10**18)
    assets = [
        {
            "network": net.key,
            "symbol": net.native_symbol,
            "token_address": None,
            "amount": str(native_amount),
            "coingecko_id": net.native_coingecko_id,
        }
    ]
    for row in rows:
        assets.append(
            {
                "network": net.key,
                "symbol": row["symbol"],
                "token_address": row["token_address"],
                "amount": str(Decimal(row["raw_amount"]) / Decimal(10 ** row["decimals"])),
                "kind": row["catalog"].kind,
                "coingecko_id": row["catalog"].coingecko_id,
            }
        )
    pricing.price_assets(assets)
    native_price = assets[0]["price_usd"]
    holdings = [
        {
            "symbol": a["symbol"],
            "token_address": a["token_address"],
            "amount": a["amount"],
            "kind": a["kind"],
            "value_usd": a["value_usd"],
            "price_source": a["price_source"],
        }
        for a in assets[1:]
        if a["value_usd"] is not None
    ]
    holdings.sort(key=lambda h: -h["value_usd"])
    return holdings, len(rows) - len(holdings), native_price, native_amount


def _evm_address(out: Out, target: str, net) -> None:
    addr = resolve_address(target)
    client = connect(net)
    code = client.w3.eth.get_code(addr)
    nonce = client.w3.eth.get_transaction_count(addr)
    holdings, holdings_hidden, native_price, native_amount = _holdings(client, net, addr)
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
        "holdings_hidden": holdings_hidden,
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
        unpriced = f" ({holdings_hidden} unpriced hidden)" if holdings_hidden else ""
        lines.append(f"  tokens: {shown}{more}{unpriced}")
    out.emit(
        data,
        lines,
        quiet_value=kind,
        verbose_lines=[f"explorer: {data['explorer']}", f"rpc: {client.url}"],
    )


def _solana_parsed(info: dict | None) -> tuple[str | None, dict]:
    data = (info or {}).get("data")
    parsed = data.get("parsed") if isinstance(data, dict) else None
    if not isinstance(parsed, dict):
        return None, {}
    return parsed.get("type"), parsed.get("info") or {}


def _solana_kind(info: dict | None, parsed_type: str | None) -> str:
    if info is None:
        return "unfunded"
    if info.get("executable"):
        return "program"
    if parsed_type in ("mint", "account"):
        return "token_mint" if parsed_type == "mint" else "token_account"
    return "wallet" if info.get("owner") == SYSTEM_PROGRAM else "account"


def _solana_mint_profile(mint: str, details: dict) -> dict:
    token = catalog.lookup("solana", mint)
    decimals = details.get("decimals") or 0
    return {
        "symbol": token.symbol if token else None,
        "name": token.name if token else None,
        "decimals": decimals,
        "total_supply": str(Decimal(int(details.get("supply") or 0)) / Decimal(10**decimals)),
        "mint_authority": details.get("mintAuthority"),
        "freeze_authority": details.get("freezeAuthority"),
    }


def _solana_holdings(addr: str) -> tuple[list[dict], int, float | None, Decimal]:
    assets = pricing.price_assets(scan_solana(addr))
    native = next((a for a in assets if a["token_address"] is None), None)
    holdings = [
        {k: a.get(k) for k in ("symbol", "token_address", "amount", "kind", "value_usd", "price_source")}
        for a in assets
        if a["token_address"] and a["value_usd"] is not None
    ]
    holdings.sort(key=lambda h: -h["value_usd"])
    hidden = sum(1 for a in assets if a["token_address"] and a["value_usd"] is None)
    native_price = native["price_usd"] if native else coingecko.try_price_usd("solana")
    return holdings, hidden, native_price, Decimal(native["amount"]) if native else Decimal(0)


def _solana_address(out: Out, target: str, net) -> None:
    addr = solana.resolve_solana_address(target)
    info = solana.account_info(addr)
    parsed_type, details = _solana_parsed(info)
    kind = _solana_kind(info, parsed_type)
    owner = (info or {}).get("owner")
    upgrade_authority, deployed_slot = None, None
    if kind == "program" and details.get("programData"):
        upgrade_authority, deployed_slot = solana.program_data_header(details["programData"])
    mint = _solana_mint_profile(addr, details) if kind == "token_mint" else None
    token_account = None
    if kind == "token_account":
        amount = details.get("tokenAmount") or {}
        token_account = {
            "mint": details.get("mint"),
            "symbol": _solana_symbol(details.get("mint")),
            "owner": details.get("owner"),
            "amount": amount.get("uiAmountString") or "0",
        }
    if kind in ("wallet", "account"):
        holdings, hidden, price, amount = _solana_holdings(addr)
    else:
        holdings, hidden = [], 0
        price = coingecko.try_price_usd("solana")
        amount = solana.lamports_to_sol((info or {}).get("lamports") or 0)
    value = float(amount) * price if price is not None else None
    data = {
        "address": addr,
        "input": target,
        "network": net.key,
        "type": kind,
        "owner_program": owner,
        "owner_program_name": solana.PROGRAM_LABELS.get(owner) if owner else None,
        "program_name": solana.PROGRAM_LABELS.get(addr) if kind == "program" else None,
        "upgrade_authority": upgrade_authority,
        "upgradeable": bool(details.get("programData")) if kind == "program" else None,
        "last_deploy_slot": deployed_slot,
        "mint": mint,
        "token_account": token_account,
        "native_amount": str(amount),
        "native_value_usd": value,
        "holdings": holdings,
        "holdings_hidden": hidden,
        "explorer": f"{net.explorer}/account/{addr}",
    }
    what = {
        "unfunded": "unfunded account",
        "wallet": "wallet (system account)",
        "token_account": "SPL token account",
        "account": f"account owned by {solana.PROGRAM_LABELS.get(owner, owner)}",
    }.get(kind)
    if kind == "program":
        label = solana.PROGRAM_LABELS.get(addr)
        what = f"program{f' ({label})' if label else ''}"
        what += f", upgradeable by {upgrade_authority}" if upgrade_authority else (
            ", immutable" if details.get("programData") else ""
        )
    if mint:
        what = f"SPL token mint ({solana.PROGRAM_LABELS.get(owner, owner)})"
    lines = [f"{short_addr(addr)} on Solana: {what}"]
    if mint:
        lines.append(
            f"  token: {mint['name'] or mint['symbol'] or short_addr(addr)}"
            + (f" ({mint['symbol']})" if mint["symbol"] else "")
            + f", {mint['decimals']} decimals, supply {fmt_amount(mint['total_supply'])}"
        )
        lines.append(
            f"  mint authority: {mint['mint_authority'] or 'none (fixed supply)'}, "
            f"freeze authority: {mint['freeze_authority'] or 'none'}"
        )
    if token_account:
        lines.append(
            f"  holds {fmt_amount(token_account['amount'])} {token_account['symbol']} for {token_account['owner']}"
        )
    native_line = f"  native: {fmt_amount(amount)} SOL"
    if value is not None:
        native_line += f" (~{fmt_usd(value)})"
    lines.append(native_line)
    if holdings:
        shown = ", ".join(f"{fmt_amount(h['amount'])} {h['symbol']} (~{fmt_usd(h['value_usd'])})" for h in holdings[:5])
        more = f" (+{len(holdings) - 5} more)" if len(holdings) > 5 else ""
        unpriced = f" ({hidden} unpriced hidden)" if hidden else ""
        lines.append(f"  tokens: {shown}{more}{unpriced}")
    out.emit(
        data,
        lines,
        quiet_value=kind,
        verbose_lines=[
            f"owner program: {owner}",
            *([f"last deploy slot: {deployed_slot}"] if deployed_slot else []),
            f"explorer: {data['explorer']}",
        ],
    )


def address(
    target: Annotated[str, typer.Argument(help="address (0x, Solana base58, Tron T…), ENS, or .sol name")],
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Inspect an address: EOA vs contract vs program, proxies, activity, holdings."""
    out = Out(json_out, quiet, verbose, format)
    value = target.strip()
    if tron.looks_like_tron(value):
        return tron_chain.address(out, value, resolve_network("tron"))
    if solana.looks_like_solana(value):
        net = resolve_network("solana")
        return _solana_address(out, value, net)
    net = resolve_network(network)
    if net.kind == "solana":
        return _solana_address(out, value, net)
    if net.kind == "tron":
        return tron_chain.address(out, value, net)
    _evm_address(out, value, net)
