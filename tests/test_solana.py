import pytest

from chainq.errors import ChainqError
from chainq.networks import resolve_network
from chainq.solana import base58_decode, is_signature, is_solana_address, resolve_solana_address
from chainq.tokens import SOLANA_TOKENS, resolve_token

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def test_network_resolves():
    net = resolve_network("sol")
    assert net.key == "solana"
    assert net.kind == "solana"


def test_base58_decode_system_program():
    assert base58_decode("11111111111111111111111111111111") == b"\x00" * 32


def test_is_solana_address():
    assert is_solana_address(USDC_MINT)
    assert not is_solana_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    assert not is_solana_address("vitalik.eth")
    assert not is_solana_address("short")


def test_resolve_solana_address_rejects_invalid():
    with pytest.raises(ChainqError):
        resolve_solana_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")


def test_is_signature():
    assert not is_signature(USDC_MINT)
    assert is_signature("5" * 87)


def test_resolve_token_symbol():
    assert resolve_token("USDC", resolve_network("solana")) == USDC_MINT


def test_resolve_token_passthrough_mint():
    assert resolve_token(USDC_MINT, resolve_network("solana")) == USDC_MINT


def test_resolve_token_unknown():
    with pytest.raises(ChainqError):
        resolve_token("notatoken", resolve_network("solana"))


def test_all_mints_are_valid_pubkeys():
    for mint in SOLANA_TOKENS.values():
        assert is_solana_address(mint)
