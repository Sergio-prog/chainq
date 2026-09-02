import json
from decimal import Decimal

from eth_abi import decode, encode
from eth_account.messages import encode_defunct
from eth_utils import keccak
from web3 import Web3

from chainq.errors import ChainqError


def parse_abi_types(value: str) -> list[str]:
    types = []
    start = 0
    depth = 0
    for index, char in enumerate(value):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            types.append(value[start:index].strip())
            start = index + 1
    final = value[start:].strip()
    if final:
        types.append(final)
    return types


def parse_signature(signature: str) -> tuple[str, list[str]]:
    name, separator, tail = signature.strip().partition("(")
    if not separator or not tail.endswith(")") or not name:
        raise ChainqError("signature must look like balanceOf(address)")
    return name, parse_abi_types(tail[:-1])


def parse_values(value: str | None) -> list:
    if value is None:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ChainqError(f"arguments must be a JSON array: {exc.msg}") from None
    if not isinstance(parsed, list):
        raise ChainqError("arguments must be a JSON array")
    return parsed


def normalize_values(types: list[str], values: list) -> list:
    if len(types) != len(values):
        raise ChainqError(f"expected {len(types)} values, got {len(values)}")
    normalized = []
    for abi_type, value in zip(types, values, strict=True):
        if abi_type == "address":
            normalized.append(Web3.to_checksum_address(value))
        elif abi_type.startswith("bytes") and isinstance(value, str) and value.startswith("0x"):
            normalized.append(bytes.fromhex(value[2:]))
        else:
            normalized.append(value)
    return normalized


def encode_abi(types: list[str], values: list) -> bytes:
    try:
        return encode(types, normalize_values(types, values))
    except ChainqError:
        raise
    except Exception as exc:
        raise ChainqError(f"ABI encode failed: {exc}") from None


def decode_abi(types: list[str], data: str) -> tuple:
    try:
        raw = bytes.fromhex(data.removeprefix("0x"))
        return decode(types, raw)
    except Exception as exc:
        raise ChainqError(f"ABI decode failed: {exc}") from None


def calldata(signature: str, arguments: str | None) -> str:
    _, types = parse_signature(signature)
    selector = keccak(text=signature)[:4]
    return "0x" + (selector + encode_abi(types, parse_values(arguments))).hex()


def json_value(value):
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, tuple):
        return [json_value(item) for item in value]
    return value


def scale_to_base(value: str, decimals: int) -> int:
    scaled = Decimal(value) * Decimal(10**decimals)
    if scaled != scaled.to_integral_value():
        raise ChainqError(f"{value} has more than {decimals} decimal places")
    return int(scaled)


def scale_from_base(value: str, decimals: int) -> Decimal:
    return Decimal(value) / Decimal(10**decimals)


def hash_message(value: str) -> str:
    message = encode_defunct(text=value)
    return "0x" + Web3.keccak(b"\x19" + message.version + message.header + message.body).hex()
