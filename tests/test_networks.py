import pytest

from chainq.errors import ChainqError
from chainq.networks import NETWORKS, resolve_network


def test_resolve_by_key():
    assert resolve_network("ethereum").chain_id == 1


def test_resolve_by_alias():
    assert resolve_network("arb").key == "arbitrum"
    assert resolve_network("op").key == "optimism"
    assert resolve_network("matic").key == "polygon"


def test_resolve_by_chain_id():
    assert resolve_network("8453").key == "base"


def test_unknown_network():
    with pytest.raises(ChainqError):
        resolve_network("dogechain")


def test_all_networks_have_rpc_urls():
    for net in NETWORKS.values():
        assert net.rpc_urls
        assert net.explorer.startswith("https://")
