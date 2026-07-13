import json
from datetime import UTC, datetime
from typing import Annotated

import typer
from web3 import Web3
from web3.exceptions import Web3RPCError

from chainq.errors import ChainqError
from chainq.evm import calldata, decode_abi, json_value, parse_abi_types
from chainq.fmt import fmt_amount, short_addr
from chainq.networks import resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.rpc import connect, resolve_address

NetworkOpt = Annotated[str, typer.Option("--network", "-n", help="EVM network key, alias, or chain id")]


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
    timestamp: Annotated[str, typer.Argument(help="Unix timestamp or ISO-8601 datetime")],
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Find the block closest to a timestamp."""
    try:
        target = int(timestamp)
    except ValueError:
        try:
            target = int(datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp())
        except ValueError:
            raise ChainqError("timestamp must be Unix seconds or ISO-8601") from None
    net, client = _client(network)
    latest = client.w3.eth.get_block("latest")
    sample_number = max(latest["number"] - 5000, 0)
    try:
        sample = client.w3.eth.get_block(sample_number)
    except Web3RPCError as exc:
        raise ChainqError(f"RPC cannot serve historical blocks on {net.name}: {exc}") from None
    elapsed = latest["timestamp"] - sample["timestamp"]
    seconds_per_block = max(elapsed / max(latest["number"] - sample_number, 1), 0.1)
    guess = round(latest["number"] - (latest["timestamp"] - target) / seconds_per_block)
    guess = min(max(guess, 0), latest["number"])
    blocks = {latest["number"]: latest, sample["number"]: sample}
    for _ in range(32):
        try:
            current = client.w3.eth.get_block(guess)
        except Web3RPCError as exc:
            raise ChainqError(f"RPC cannot serve the required historical block on {net.name}: {exc}") from None
        blocks[current["number"]] = current
        difference = current["timestamp"] - target
        if abs(difference) <= seconds_per_block:
            break
        step = max(round(abs(difference) / seconds_per_block), 1)
        next_guess = current["number"] - step if difference > 0 else current["number"] + step
        next_guess = min(max(next_guess, 0), latest["number"])
        if next_guess == guess:
            break
        guess = next_guess
    result = min(blocks.values(), key=lambda item: abs(item["timestamp"] - target))
    actual = datetime.fromtimestamp(result["timestamp"], tz=UTC)
    data = {
        "network": net.key,
        "block_number": result["number"],
        "timestamp": result["timestamp"],
        "datetime": actual.isoformat(),
        "difference_seconds": result["timestamp"] - target,
    }
    Out(json_out, quiet, verbose, format).emit(
        data,
        f"Closest {net.name} block: {result['number']:,} at {actual:%Y-%m-%d %H:%M:%S UTC} ({data['difference_seconds']:+d}s)",
        quiet_value=result["number"],
        verbose_lines=[f"rpc: {client.url}"],
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
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Get an account transaction count."""
    net, client = _client(network)
    resolved = resolve_address(address)
    value = client.w3.eth.get_transaction_count(resolved, _block_ref(block_ref))
    Out(json_out, quiet, verbose, format).emit(
        {"network": net.key, "address": resolved, "nonce": value, "block": block_ref},
        f"{short_addr(resolved)} nonce on {net.name}: {value}",
        quiet_value=value,
        verbose_lines=[f"address: {resolved}", f"rpc: {client.url}"],
    )


def code(
    address: Annotated[str, typer.Argument(help="contract address or ENS name")],
    block_ref: Annotated[str, typer.Option("--block", help="block number or tag")] = "latest",
    network: NetworkOpt = "ethereum",
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Get contract bytecode."""
    net, client = _client(network)
    resolved = resolve_address(address)
    value = Web3.to_hex(client.w3.eth.get_code(resolved, _block_ref(block_ref)))
    data = {"network": net.key, "address": resolved, "bytecode": value, "size_bytes": len(bytes.fromhex(value[2:]))}
    Out(json_out, quiet, verbose, format).emit(
        data,
        f"{short_addr(resolved)} on {net.name}: {data['size_bytes']:,} bytes of code",
        quiet_value=value,
        verbose_lines=[f"address: {resolved}", f"rpc: {client.url}"],
    )


def storage(
    address: Annotated[str, typer.Argument(help="contract address or ENS name")],
    slot: Annotated[str, typer.Argument(help="storage slot (decimal or hex)")],
    block_ref: Annotated[str, typer.Option("--block", help="block number or tag")] = "latest",
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
    value = Web3.to_hex(client.w3.eth.get_storage_at(resolved, slot_number, _block_ref(block_ref)))
    data = {"network": net.key, "address": resolved, "slot": slot_number, "value": value, "block": block_ref}
    Out(json_out, quiet, verbose, format).emit(
        data,
        f"{short_addr(resolved)} slot {slot_number} on {net.name}: {value}",
        quiet_value=value,
        verbose_lines=[f"address: {resolved}", f"rpc: {client.url}"],
    )


def call(
    address: Annotated[str, typer.Argument(help="contract address or ENS name")],
    signature: Annotated[str, typer.Argument(help="function signature, e.g. balanceOf(address)")],
    arguments: Annotated[str | None, typer.Argument(help="JSON array of function arguments")] = None,
    returns: Annotated[str | None, typer.Option("--returns", help="comma-separated output ABI types")] = None,
    block_ref: Annotated[str, typer.Option("--block", help="block number or tag")] = "latest",
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
    raw = Web3.to_hex(client.w3.eth.call({"to": resolved, "data": data_hex}, _block_ref(block_ref)))
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
    }
    display = json.dumps(decoded, separators=(",", ":")) if decoded is not None else raw
    Out(json_out, quiet, verbose, format).emit(
        data,
        f"{signature} on {short_addr(resolved)}: {display}",
        quiet_value=display,
        verbose_lines=[f"calldata: {data_hex}", f"rpc: {client.url}"],
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
