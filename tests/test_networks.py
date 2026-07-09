import pytest

from chainq.errors import ChainqError
from chainq.networks import NETWORKS, resolve_network


def test_resolve_by_key():
    assert resolve_network("ethereum").chain_id == 1
    assert resolve_network("robinhood").chain_id == 4663


def test_resolve_by_alias():
    assert resolve_network("arb").key == "arbitrum"
    assert resolve_network("op").key == "optimism"
    assert resolve_network("matic").key == "polygon"
    assert resolve_network("rh").key == "robinhood"
    assert resolve_network("robinhood-chain").key == "robinhood"


def test_resolve_by_chain_id():
    assert resolve_network("8453").key == "base"
    assert resolve_network("4663").key == "robinhood"


def test_unknown_network():
    with pytest.raises(ChainqError):
        resolve_network("dogechain")


def test_all_networks_have_rpc_urls():
    for net in NETWORKS.values():
        assert net.rpc_urls
        assert net.explorer.startswith("https://")


def test_all_networks_have_unique_chain_ids():
    chain_ids = [net.chain_id for net in NETWORKS.values()]
    assert len(chain_ids) == len(set(chain_ids))
