import json
from datetime import UTC, datetime
from typing import Annotated

import typer
from web3 import Web3

from chainq.blocktime import BlockAt, block_at, format_time, parse_when
from chainq.errors import ChainqError
from chainq.evm import calldata, decode_abi, json_value, parse_abi_types
from chainq.evm_address import resolve_address
from chainq.fmt import dim, fmt_amount, short_addr
from chainq.networks import resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.rpc import connect

NetworkOpt = Annotated[str, typer.Option("--network", "-n", help="EVM network key, alias, or chain id")]
AtOpt = Annotated[
    str | None,
    typer.Option("--at", help="read state as of a time: ISO-8601, Unix seconds, or '3d ago' (last block at or before it)"),
]


def _client(network: str):
    net = resolve_network(network)
    if net.kind != "evm":
        raise ChainqError("this command requires an EVM network")
    return net, connect(net)


def _block_ref(value: str) -> str | int:
    if value in {"latest", "earliest", "pending", "safe", "finalized"}:
        return value
    try:
        return int(value, 0)
    except ValueError:
        raise ChainqError(f"invalid block reference '{value}'") from None


def state_block(client, block_ref: str, at: str | None) -> tuple[str | int, BlockAt | None]:
    if at is None:
        return _block_ref(block_ref), None
    if block_ref != "latest":
        raise ChainqError("use either --block or --at, not both")
    found = block_at(client, parse_when(at))
    return found.block.number, found


def at_fields(found: BlockAt | None) -> dict:
    if found is None:
        return {}
    return {"at": datetime.fromtimestamp(found.target, tz=UTC).isoformat(), "block_timestamp": found.block.timestamp}


def at_suffix(found: BlockAt | None) -> str:
    if found is None:
        return ""
    return dim(f" @ block {found.block.number:,} ({format_time(found.block.timestamp)})")


def at_verbose(found: BlockAt | None) -> list[str]:
    if found is None:
        return []
    return [
        f"block: {found.block.number:,} at {format_time(found.block.timestamp)}"
        f" (resolved in {found.rounds} rounds, {found.fetched} headers, {found.seconds * 1000:.0f} ms)"
    ]


def _serializable(value):
    return json.loads(Web3.to_json(value))


def block_number(
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Get the latest block number."""
    net, client = _client(network)
    number = client.w3.eth.block_number
    Out(json_out, quiet, verbose, format).emit(
        {"network": net.key, "block_number": number},
        f"{net.name} latest block: {number:,}",
        quiet_value=number,
        verbose_lines=[f"rpc: {client.url}"],
    )


def block(
    block_ref: Annotated[str, typer.Argument(help="block number (decimal/hex) or tag")] = "latest",
    transactions: Annotated[bool, typer.Option("--transactions", help="include full transactions")] = False,
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Get block information."""
    net, client = _client(network)
    result = client.w3.eth.get_block(_block_ref(block_ref), full_transactions=transactions)
    data = _serializable(result)
    timestamp = datetime.fromtimestamp(result["timestamp"], tz=UTC)
    lines = [
        f"{net.name} block {result['number']:,}: {len(result['transactions'])} txs at {timestamp:%Y-%m-%d %H:%M:%S UTC}",
        f"  hash {Web3.to_hex(result['hash'])}, gas {result['gasUsed']:,}/{result['gasLimit']:,}",
    ]
    Out(json_out, quiet, verbose, format).emit(
        data, lines, quiet_value=result["number"], verbose_lines=[f"rpc: {client.url}"]
    )


def find_block(
    when: Annotated[str, typer.Argument(help="ISO-8601 datetime, Unix seconds, or '3d ago'")],
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Find the block closest to a time (and the last block at or before it)."""
    target = parse_when(when)
    net, client = _client(network)
    found = block_at(client, target)
    closest = found.closest
    data = {
        "network": net.key,
        "target": target,
        "block_number": closest.number,
        "timestamp": closest.timestamp,
        "datetime": datetime.fromtimestamp(closest.timestamp, tz=UTC).isoformat(),
        "difference_seconds": closest.timestamp - target,
        "at_or_before": found.block.number,
        "at_or_before_timestamp": found.block.timestamp,
        "rounds": found.rounds,
        "headers_fetched": found.fetched,
        "elapsed_ms": round(found.seconds * 1000),
    }
    text = (
        f"{dim(f'Closest {net.name} block:')} {closest.number:,} {dim('at')} {format_time(closest.timestamp)}"
        f" {dim(f'({data['difference_seconds']:+d}s)')}"
    )
    if closest != found.block:
        text += dim(f"  at-or-before: {found.block.number:,}")
    Out(json_out, quiet, verbose, format).emit(
        data,
        text,
        quiet_value=closest.number,
        verbose_lines=[*at_verbose(found), f"rpc: {client.url}"],
    )


def client(
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Get the connected execution client version."""
    net, rpc_client = _client(network)
    version = rpc_client.w3.client_version
    Out(json_out, quiet, verbose, format).emit(
        {"network": net.key, "client_version": version},
        f"{net.name} client: {version}",
        quiet_value=version,
        verbose_lines=[f"rpc: {rpc_client.url}"],
    )


def chain_id(
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Get the connected EVM chain ID."""
    net, client = _client(network)
    value = client.w3.eth.chain_id
    Out(json_out, quiet, verbose, format).emit(
        {"network": net.key, "chain_id": value},
        f"{net.name} chain ID: {value}",
        quiet_value=value,
        verbose_lines=[f"rpc: {client.url}"],
    )


def nonce(
    address: Annotated[str, typer.Argument(help="address or ENS name")],
    block_ref: Annotated[str, typer.Option("--block", help="block number or tag")] = "latest",
    at: AtOpt = None,
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Get an account transaction count."""
    net, client = _client(network)
    resolved = resolve_address(address)
    block, found = state_block(client, block_ref, at)
    value = client.w3.eth.get_transaction_count(resolved, block)
    Out(json_out, quiet, verbose, format).emit(
        {"network": net.key, "address": resolved, "nonce": value, "block": block, **at_fields(found)},
        f"{short_addr(resolved)} nonce on {net.name}: {value}{at_suffix(found)}",
        quiet_value=value,
        verbose_lines=[f"address: {resolved}", *at_verbose(found), f"rpc: {client.url}"],
    )


def code(
    address: Annotated[str, typer.Argument(help="contract address or ENS name")],
    block_ref: Annotated[str, typer.Option("--block", help="block number or tag")] = "latest",
    at: AtOpt = None,
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Get contract bytecode."""
    net, client = _client(network)
    resolved = resolve_address(address)
    block, found = state_block(client, block_ref, at)
    value = Web3.to_hex(client.w3.eth.get_code(resolved, block))
    data = {
        "network": net.key,
        "address": resolved,
        "bytecode": value,
        "size_bytes": len(bytes.fromhex(value[2:])),
        "block": block,
        **at_fields(found),
    }
    Out(json_out, quiet, verbose, format).emit(
        data,
        f"{short_addr(resolved)} on {net.name}: {data['size_bytes']:,} bytes of code{at_suffix(found)}",
        quiet_value=value,
        verbose_lines=[f"address: {resolved}", *at_verbose(found), f"rpc: {client.url}"],
    )


def storage(
    address: Annotated[str, typer.Argument(help="contract address or ENS name")],
    slot: Annotated[str, typer.Argument(help="storage slot (decimal or hex)")],
    block_ref: Annotated[str, typer.Option("--block", help="block number or tag")] = "latest",
    at: AtOpt = None,
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Get the 32-byte value at a contract storage slot."""
    net, client = _client(network)
    resolved = resolve_address(address)
    try:
        slot_number = int(slot, 0)
    except ValueError:
        raise ChainqError(f"invalid storage slot '{slot}'") from None
    block, found = state_block(client, block_ref, at)
    value = Web3.to_hex(client.w3.eth.get_storage_at(resolved, slot_number, block))
    data = {"network": net.key, "address": resolved, "slot": slot_number, "value": value, "block": block, **at_fields(found)}
    Out(json_out, quiet, verbose, format).emit(
        data,
        f"{short_addr(resolved)} slot {slot_number} on {net.name}: {value}{at_suffix(found)}",
        quiet_value=value,
        verbose_lines=[f"address: {resolved}", *at_verbose(found), f"rpc: {client.url}"],
    )


def call(
    address: Annotated[str, typer.Argument(help="contract address or ENS name")],
    signature: Annotated[str, typer.Argument(help="function signature, e.g. balanceOf(address)")],
    arguments: Annotated[str | None, typer.Argument(help="JSON array of function arguments")] = None,
    returns: Annotated[str | None, typer.Option("--returns", help="comma-separated output ABI types")] = None,
    block_ref: Annotated[str, typer.Option("--block", help="block number or tag")] = "latest",
    at: AtOpt = None,
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Call a contract function without an ABI file."""
    net, client = _client(network)
    resolved = resolve_address(address)
    data_hex = calldata(signature, arguments)
    block, found = state_block(client, block_ref, at)
    raw = Web3.to_hex(client.w3.eth.call({"to": resolved, "data": data_hex}, block))
    decoded = None
    if returns:
        decoded = json_value(decode_abi(parse_abi_types(returns), raw))
    data = {
        "network": net.key,
        "address": resolved,
        "signature": signature,
        "calldata": data_hex,
        "raw": raw,
        "decoded": decoded,
        "block": block,
        **at_fields(found),
    }
    display = json.dumps(decoded, separators=(",", ":")) if decoded is not None else raw
    Out(json_out, quiet, verbose, format).emit(
        data,
        f"{signature} on {short_addr(resolved)}: {display}{at_suffix(found)}",
        quiet_value=display,
        verbose_lines=[f"calldata: {data_hex}", *at_verbose(found), f"rpc: {client.url}"],
    )


def estimate(
    address: Annotated[str, typer.Argument(help="destination contract address or ENS name")],
    signature: Annotated[str, typer.Argument(help="function signature")],
    arguments: Annotated[str | None, typer.Argument(help="JSON array of function arguments")] = None,
    sender: Annotated[str | None, typer.Option("--from", help="sender address or ENS name")] = None,
    value: Annotated[int, typer.Option("--value", help="native value in wei")] = 0,
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Estimate gas for a contract function call."""
    net, client = _client(network)
    resolved = resolve_address(address)
    transaction = {"to": resolved, "data": calldata(signature, arguments), "value": value}
    if sender:
        transaction["from"] = resolve_address(sender)
    gas = client.w3.eth.estimate_gas(transaction)
    Out(json_out, quiet, verbose, format).emit(
        {"network": net.key, "address": resolved, "signature": signature, "gas": gas, "transaction": transaction},
        f"Estimated {signature} gas on {net.name}: {fmt_amount(gas)}",
        quiet_value=gas,
        verbose_lines=[f"rpc: {client.url}"],
    )
