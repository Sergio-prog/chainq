import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

import typer
from web3.exceptions import TransactionNotFound
from web3.types import RPCEndpoint

from chainq.errors import ChainqError
from chainq.fmt import fmt_amount, fmt_gwei, fmt_usd, short_addr
from chainq.networks import NETWORKS, resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import coingecko
from chainq.rpc import connect, erc20, resolve_address
from chainq.tokens import resolve_token

NetworkOpt = Annotated[str, typer.Option("--network", "-n", help="network key, alias, or chain id")]


def networks(
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text"
):
    """List supported networks with chain ids and aliases."""
    out = Out(json_out, quiet, verbose, format)
    data = [
        {
            "key": net.key,
            "name": net.name,
            "chain_id": net.chain_id,
            "native_symbol": net.native_symbol,
            "aliases": list(net.aliases),
            "rpc_urls": list(net.rpc_urls),
            "explorer": net.explorer,
        }
        for net in NETWORKS.values()
    ]
    lines = [
        f"{net.key}  (chain id {net.chain_id}, native {net.native_symbol})"
        + (f"  aliases: {', '.join(net.aliases)}" if net.aliases else "")
        for net in NETWORKS.values()
    ]
    verbose_lines = [f"{net.key}: {', '.join(net.rpc_urls)}" for net in NETWORKS.values()]
    out.emit(data, lines, quiet_value="\n".join(NETWORKS), verbose_lines=verbose_lines)


def balance(
    address: Annotated[str, typer.Argument(help="wallet address or ENS name")],
    coin: Annotated[str | None, typer.Option("--coin", "-c", help="token symbol or ERC-20 address; omit for native")] = None,
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Get native or ERC-20 token balance of an address."""
    out = Out(json_out, quiet, verbose, format)
    net = resolve_network(network)
    addr = resolve_address(address)
    client = connect(net)
    if coin is None:
        wei = client.w3.eth.get_balance(addr)
        amount = Decimal(wei) / Decimal(10**18)
        symbol = net.native_symbol
        price = coingecko.try_price_usd(net.native_coingecko_id)
        token_address = None
    else:
        token_address = resolve_token(coin, net)
        contract = erc20(client, token_address)
        decimals = contract.functions.decimals().call()
        symbol = contract.functions.symbol().call()
        raw = contract.functions.balanceOf(addr).call()
        amount = Decimal(raw) / Decimal(10**decimals)
        cg_id = coingecko.SYMBOL_TO_ID.get(coin.lower()) if not coin.startswith("0x") else None
        price = coingecko.try_price_usd(cg_id)
    usd_value = float(amount) * price if price is not None else None
    data = {
        "address": addr,
        "input": address,
        "network": net.key,
        "symbol": symbol,
        "token_address": token_address,
        "amount": str(amount),
        "price_usd": price,
        "value_usd": usd_value,
    }
    label = f"{address} ({short_addr(addr)})" if address != addr else short_addr(addr)
    text = f"{label} on {net.name}: {fmt_amount(amount)} {symbol}"
    if usd_value is not None:
        text += f" (~{fmt_usd(usd_value)})"
    out.emit(
        data,
        text,
        quiet_value=amount,
        verbose_lines=[
            f"rpc: {client.url}",
            f"address: {addr}",
            *([f"token: {token_address}"] if token_address else []),
            *([f"price used: {fmt_usd(price)} [coingecko]"] if price is not None else []),
        ],
    )


def gas(
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Current gas price, base fee, and estimated native-transfer cost in USD."""
    out = Out(json_out, quiet, verbose, format)
    net = resolve_network(network)
    client = connect(net)
    gas_price = client.w3.eth.gas_price
    base_fee = None
    priority_p50 = None
    try:
        hist = client.w3.eth.fee_history(1, "latest", [25, 50, 90])
        base_fee = hist["baseFeePerGas"][-1]
        rewards = hist.get("reward") or []
        if rewards:
            priority_p50 = rewards[0][1]
    except Exception:
        pass
    price = coingecko.try_price_usd(net.native_coingecko_id)
    transfer_cost_usd = (21000 * gas_price / 1e18) * price if price is not None else None
    data = {
        "network": net.key,
        "gas_price_wei": gas_price,
        "gas_price_gwei": gas_price / 1e9,
        "base_fee_gwei": base_fee / 1e9 if base_fee is not None else None,
        "priority_fee_p50_gwei": priority_p50 / 1e9 if priority_p50 is not None else None,
        "native_price_usd": price,
        "transfer_cost_usd": transfer_cost_usd,
    }
    text = f"{net.name} gas: {fmt_gwei(gas_price)}"
    if base_fee is not None:
        text += f" (base {fmt_gwei(base_fee)}"
        text += f", priority p50 {fmt_gwei(priority_p50)})" if priority_p50 is not None else ")"
    if transfer_cost_usd is not None:
        text += f" — native transfer ≈ {fmt_usd(transfer_cost_usd)}"
    out.emit(data, text, quiet_value=gas_price / 1e9, verbose_lines=[f"rpc: {client.url}"])


def tx(
    tx_hash: Annotated[str, typer.Argument(help="transaction hash")],
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Look up a transaction: status, parties, value, fee, block."""
    out = Out(json_out, quiet, verbose, format)
    net = resolve_network(network)
    client = connect(net)
    try:
        transaction = client.w3.eth.get_transaction(tx_hash)
    except TransactionNotFound:
        raise ChainqError(f"transaction {tx_hash} not found on {net.name} (check the hash and --network)") from None
    receipt = None
    if transaction.get("blockNumber") is not None:
        try:
            receipt = client.w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            receipt = None
    if receipt is None:
        status = "pending"
    else:
        status = "success" if receipt["status"] == 1 else "failed"
    value = Decimal(transaction["value"]) / Decimal(10**18)
    fee = None
    if receipt is not None:
        fee = Decimal(receipt["gasUsed"] * receipt.get("effectiveGasPrice", transaction.get("gasPrice", 0))) / Decimal(10**18)
    timestamp = None
    if transaction.get("blockNumber") is not None:
        block = client.w3.eth.get_block(transaction["blockNumber"])
        timestamp = datetime.fromtimestamp(block["timestamp"], tz=UTC)
    price = coingecko.try_price_usd(net.native_coingecko_id)
    to_address = transaction.get("to")
    data = {
        "hash": transaction["hash"].hex(),
        "network": net.key,
        "status": status,
        "from": transaction["from"],
        "to": to_address,
        "value": str(value),
        "value_usd": float(value) * price if price is not None else None,
        "fee": str(fee) if fee is not None else None,
        "fee_usd": float(fee) * price if fee is not None and price is not None else None,
        "block": transaction.get("blockNumber"),
        "timestamp": timestamp.isoformat() if timestamp else None,
        "nonce": transaction["nonce"],
        "gas_used": receipt["gasUsed"] if receipt else None,
        "gas_limit": transaction["gas"],
        "explorer": f"{net.explorer}/tx/0x{transaction['hash'].hex().removeprefix('0x')}",
    }
    lines = [
        f"Tx {short_addr(tx_hash)} on {net.name}: {status}",
        f"  {transaction['from']} → {to_address or 'contract creation'}",
        f"  value {fmt_amount(value)} {net.native_symbol}"
        + (f" (~{fmt_usd(data['value_usd'])})" if data["value_usd"] else "")
        + (f", fee {fmt_amount(fee)} {net.native_symbol}" if fee is not None else "")
        + (f" (~{fmt_usd(data['fee_usd'])})" if data["fee_usd"] else ""),
    ]
    if data["block"] is not None:
        when = f" at {timestamp.strftime('%Y-%m-%d %H:%M UTC')}" if timestamp else ""
        lines.append(f"  block {data['block']}{when}")
    out.emit(
        data,
        lines,
        quiet_value=status,
        verbose_lines=[
            f"nonce: {data['nonce']}, gas used: {data['gas_used']}/{data['gas_limit']}",
            f"explorer: {data['explorer']}",
            f"rpc: {client.url}",
        ],
    )


def rpc(
    method: Annotated[str, typer.Argument(help="JSON-RPC method, e.g. eth_blockNumber")],
    params: Annotated[list[str] | None, typer.Argument(help="params; JSON literals are parsed, rest stay strings")] = None,
    network: NetworkOpt = "ethereum",
):
    """Raw JSON-RPC escape hatch; prints the JSON result."""
    net = resolve_network(network)
    client = connect(net)
    parsed = []
    for param in params or []:
        try:
            parsed.append(json.loads(param))
        except json.JSONDecodeError:
            parsed.append(param)
    response = client.w3.provider.make_request(RPCEndpoint(method), parsed)
    if "error" in response:
        raise ChainqError(f"rpc error from {client.url}: {response['error']}")
    print(json.dumps(response.get("result"), indent=2, default=str))
