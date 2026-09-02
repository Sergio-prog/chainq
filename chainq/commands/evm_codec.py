import json
from typing import Annotated

import typer
from ens.utils import normal_name_to_hash
from eth_utils import event_signature_to_log_topic, function_signature_to_4byte_selector, keccak
from web3 import Web3

from chainq.errors import ChainqError
from chainq.evm import decode_abi, encode_abi, json_value, parse_abi_types, parse_values
from chainq.evm import hash_message as eip191_hash
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt


def _emit(value, label: str, json_out: bool, quiet: bool, verbose: bool, format: str, **fields):
    Out(json_out, quiet, verbose, format).emit({**fields, "result": value}, f"{label}: {value}", quiet_value=value)


def to_hex(
    value: Annotated[str, typer.Argument(help="decimal or 0x-prefixed integer")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Convert an integer to hexadecimal."""
    try:
        result = hex(int(value, 0))
    except ValueError:
        raise ChainqError(f"invalid integer '{value}'") from None
    _emit(result, value, json_out, quiet, verbose, format, input=value)


def to_dec(
    value: Annotated[str, typer.Argument(help="hexadecimal or decimal integer")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Convert a hexadecimal integer to decimal."""
    try:
        result = int(value, 0)
    except ValueError:
        raise ChainqError(f"invalid integer '{value}'") from None
    _emit(result, value, json_out, quiet, verbose, format, input=value)


def to_wei(
    value: Annotated[str, typer.Argument(help="amount to convert")],
    unit: Annotated[str, typer.Argument(help="ether unit, e.g. ether or gwei")] = "ether",
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Convert an Ethereum unit to wei."""
    try:
        result = Web3.to_wei(value, unit)
    except Exception as exc:
        raise ChainqError(f"unit conversion failed: {exc}") from None
    _emit(result, f"{value} {unit}", json_out, quiet, verbose, format, input=value, unit=unit)


def from_wei(
    value: Annotated[int, typer.Argument(help="amount in wei")],
    unit: Annotated[str, typer.Argument(help="target unit, e.g. ether or gwei")] = "ether",
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Convert wei to an Ethereum unit."""
    try:
        result = str(Web3.from_wei(value, unit))
    except Exception as exc:
        raise ChainqError(f"unit conversion failed: {exc}") from None
    _emit(result, f"{value} wei", json_out, quiet, verbose, format, input=value, unit=unit)


def keccak256(
    value: Annotated[str, typer.Argument(help="UTF-8 text, or hex data with --hex")],
    hex_data: Annotated[bool, typer.Option("--hex", help="treat input as hex data")] = False,
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Calculate a Keccak-256 hash."""
    try:
        result = "0x" + (keccak(hexstr=value) if hex_data else keccak(text=value)).hex()
    except Exception as exc:
        raise ChainqError(f"keccak failed: {exc}") from None
    _emit(result, "keccak256", json_out, quiet, verbose, format, input=value, encoding="hex" if hex_data else "utf-8")


def sig(
    signature: Annotated[str, typer.Argument(help="canonical function signature")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Get a 4-byte function selector."""
    result = "0x" + function_signature_to_4byte_selector(signature).hex()
    _emit(result, signature, json_out, quiet, verbose, format, signature=signature)


def sig_event(
    signature: Annotated[str, typer.Argument(help="canonical event signature")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Get a 32-byte event signature topic."""
    result = "0x" + event_signature_to_log_topic(signature).hex()
    _emit(result, signature, json_out, quiet, verbose, format, signature=signature)


def shl(
    bits: Annotated[int, typer.Argument(help="number of bits")],
    value: Annotated[str, typer.Argument(help="integer to shift")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Shift an integer left."""
    try:
        result = int(value, 0) << bits
    except ValueError:
        raise ChainqError("shift value must be an integer and bits must be non-negative") from None
    _emit(result, "left shift", json_out, quiet, verbose, format, input=value, bits=bits, hex=hex(result))


def shr(
    bits: Annotated[int, typer.Argument(help="number of bits")],
    value: Annotated[str, typer.Argument(help="integer to shift")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Shift an integer right."""
    try:
        result = int(value, 0) >> bits
    except ValueError:
        raise ChainqError("shift value must be an integer and bits must be non-negative") from None
    _emit(result, "right shift", json_out, quiet, verbose, format, input=value, bits=bits, hex=hex(result))


def format_bytes32_string(
    value: Annotated[str, typer.Argument(help="UTF-8 text up to 31 bytes")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Encode a short UTF-8 string as bytes32."""
    raw = value.encode()
    if len(raw) > 31:
        raise ChainqError("bytes32 string must be at most 31 UTF-8 bytes")
    result = "0x" + raw.ljust(32, b"\x00").hex()
    _emit(result, value, json_out, quiet, verbose, format, input=value)


def parse_bytes32_string(
    value: Annotated[str, typer.Argument(help="32-byte hex value")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Decode a null-terminated bytes32 string."""
    try:
        raw = bytes.fromhex(value.removeprefix("0x"))
        if len(raw) != 32:
            raise ValueError
        result = raw.split(b"\x00", 1)[0].decode()
    except (ValueError, UnicodeDecodeError):
        raise ChainqError("value must be 32-byte hex containing UTF-8 text") from None
    _emit(result, value, json_out, quiet, verbose, format, input=value)


def parse_bytes32_address(
    value: Annotated[str, typer.Argument(help="32-byte ABI-padded address")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Extract an address from a 32-byte word."""
    try:
        raw = bytes.fromhex(value.removeprefix("0x"))
        if len(raw) != 32:
            raise ValueError
        result = Web3.to_checksum_address(raw[-20:])
    except Exception:
        raise ChainqError("value must be 32-byte hex") from None
    _emit(result, value, json_out, quiet, verbose, format, input=value)


def to_bytes32(
    value: Annotated[str, typer.Argument(help="hex data up to 32 bytes")],
    left: Annotated[bool, typer.Option("--left", help="pad on the left (ABI-style)")] = False,
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Pad hex data to 32 bytes."""
    try:
        raw = bytes.fromhex(value.removeprefix("0x"))
    except ValueError:
        raise ChainqError("value must be hex data") from None
    if len(raw) > 32:
        raise ChainqError("value exceeds 32 bytes")
    padded = raw.rjust(32, b"\x00") if left else raw.ljust(32, b"\x00")
    result = "0x" + padded.hex()
    _emit(result, value, json_out, quiet, verbose, format, input=value, padding="left" if left else "right")


def from_utf8(
    value: Annotated[str, typer.Argument(help="UTF-8 text")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Encode UTF-8 text as hex data."""
    result = "0x" + value.encode().hex()
    _emit(result, value, json_out, quiet, verbose, format, input=value)


def to_utf8(
    value: Annotated[str, typer.Argument(help="hex data")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Decode hex data as UTF-8 text."""
    try:
        result = bytes.fromhex(value.removeprefix("0x")).decode()
    except (ValueError, UnicodeDecodeError):
        raise ChainqError("value must be valid hex-encoded UTF-8") from None
    _emit(result, value, json_out, quiet, verbose, format, input=value)


def checksum(
    address: Annotated[str, typer.Argument(help="EVM address")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Convert an address to EIP-55 checksum form."""
    try:
        result = Web3.to_checksum_address(address)
    except Exception:
        raise ChainqError(f"invalid EVM address '{address}'") from None
    _emit(result, address, json_out, quiet, verbose, format, input=address)


def hash_message(
    value: Annotated[str, typer.Argument(help="UTF-8 message")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Hash a message using the EIP-191 personal-sign prefix."""
    result = eip191_hash(value)
    _emit(result, "EIP-191 hash", json_out, quiet, verbose, format, input=value)


def hash_zero(
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Print the zero bytes32 value."""
    result = "0x" + "00" * 32
    _emit(result, "zero hash", json_out, quiet, verbose, format)


def namehash(
    name: Annotated[str, typer.Argument(help="ENS name")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Calculate an ENS namehash."""
    try:
        result = "0x" + normal_name_to_hash(name).hex()
    except Exception as exc:
        raise ChainqError(f"invalid ENS name '{name}': {exc}") from None
    _emit(result, name, json_out, quiet, verbose, format, name=name)


def _integer_limit(bits: int, signed: bool, minimum: bool = False) -> int:
    if bits < 8 or bits > 256 or bits % 8:
        raise ChainqError("bits must be a multiple of 8 from 8 to 256")
    if not signed:
        return 2**bits - 1
    return -(2 ** (bits - 1)) if minimum else 2 ** (bits - 1) - 1


def max_int(
    bits: Annotated[int, typer.Argument(help="integer width (8..256, multiple of 8)")] = 256,
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Get the maximum signed integer."""
    result = _integer_limit(bits, True)
    _emit(result, f"int{bits} max", json_out, quiet, verbose, format, bits=bits, hex=hex(result))


def min_int(
    bits: Annotated[int, typer.Argument(help="integer width (8..256, multiple of 8)")] = 256,
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Get the minimum signed integer."""
    result = _integer_limit(bits, True, True)
    _emit(result, f"int{bits} min", json_out, quiet, verbose, format, bits=bits)


def max_uint(
    bits: Annotated[int, typer.Argument(help="integer width (8..256, multiple of 8)")] = 256,
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Get the maximum unsigned integer."""
    result = _integer_limit(bits, False)
    _emit(result, f"uint{bits} max", json_out, quiet, verbose, format, bits=bits, hex=hex(result))


def abi_encode(
    types: Annotated[str, typer.Argument(help="comma-separated ABI types")],
    values: Annotated[str, typer.Argument(help="JSON array of values")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """ABI-encode a JSON array of values."""
    parsed_types = parse_abi_types(types)
    result = "0x" + encode_abi(parsed_types, parse_values(values)).hex()
    _emit(result, "ABI encoded", json_out, quiet, verbose, format, types=parsed_types)


def abi_decode(
    types: Annotated[str, typer.Argument(help="comma-separated ABI types")],
    data: Annotated[str, typer.Argument(help="ABI-encoded hex data")],
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """ABI-decode hex data."""
    parsed_types = parse_abi_types(types)
    result = json_value(decode_abi(parsed_types, data))
    display = json.dumps(result, separators=(",", ":"))
    Out(json_out, quiet, verbose, format).emit(
        {"types": parsed_types, "result": result}, f"ABI decoded: {display}", quiet_value=display
    )
