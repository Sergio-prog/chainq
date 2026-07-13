import json

from eth_account.messages import _hash_eip191_message, encode_defunct
from typer.testing import CliRunner

from chainq.cli import app
from chainq.evm import calldata, parse_abi_types

runner = CliRunner()


def invoke(*args: str):
    result = runner.invoke(app, ["evm", *args])
    assert result.exit_code == 0, result.output
    return result


def test_evm_help_is_discoverable():
    result = invoke("--help")
    assert "EVM queries and utilities" in result.output
    assert "abi-encode" in result.output
    assert "block-number" in result.output


def test_function_selector():
    assert invoke("sig", "transfer(address,uint256)", "-q").output.strip() == "0xa9059cbb"


def test_keccak_text():
    assert invoke("keccak", "hello", "-q").output.strip() == (
        "0x1c8aff950685c2ed4bc3174f3472287b56d9517b9c948127319a09a7a36deac8"
    )


def test_eip191_message_hash():
    expected = "0x" + _hash_eip191_message(encode_defunct(text="hello")).hex()
    assert invoke("hash-message", "hello", "-q").output.strip() == expected


def test_abi_roundtrip():
    encoded = invoke("abi-encode", "string,uint256", '["chainq",42]', "-q").output.strip()
    decoded = invoke("abi-decode", "string,uint256", encoded, "--json")
    assert json.loads(decoded.output)["result"] == ["chainq", 42]


def test_calldata_encoding():
    result = calldata(
        "balanceOf(address)",
        '["0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"]',
    )
    assert result.startswith("0x70a08231")
    assert len(result) == 74


def test_nested_abi_types():
    assert parse_abi_types("address,(uint256,address),bytes32[]") == ["address", "(uint256,address)", "bytes32[]"]


def test_bytes32_string_roundtrip():
    encoded = invoke("format-bytes32-string", "chainq", "-q").output.strip()
    assert invoke("parse-bytes32-string", encoded, "-q").output.strip() == "chainq"


def test_integer_limits():
    assert invoke("max-uint", "8", "-q").output.strip() == "255"
    assert invoke("min-int", "8", "-q").output.strip() == "-128"


def test_bit_shifts():
    assert invoke("shl", "8", "1", "-q").output.strip() == "256"
    assert invoke("shr", "4", "0x100", "-q").output.strip() == "16"
