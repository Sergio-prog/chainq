import pytest
from web3 import Web3

from chainq.errors import ChainqError
from chainq.networks import NETWORKS, resolve_network
from chainq.tokens import TOKENS, resolve_token


def test_all_registry_networks_exist():
    assert set(TOKENS) <= set(NETWORKS)


def test_all_addresses_are_valid_checksums():
    for chain_tokens in TOKENS.values():
        for address in chain_tokens.values():
            assert Web3.to_checksum_address(address) == address


def test_resolve_symbol():
    assert resolve_token("USDT", resolve_network("ethereum")) == "0xdAC17F958D2ee523a2206206994597C13D831ec7"


def test_resolve_passthrough_address():
    address = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    assert resolve_token(address, resolve_network("base")) == address


def test_unknown_symbol():
    with pytest.raises(ChainqError):
        resolve_token("notatoken", resolve_network("ethereum"))
