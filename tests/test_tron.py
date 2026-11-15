import pytest

from chainq import tron
from chainq.commands import tron_chain
from chainq.commands.portfolio import _resolve_scan_target
from chainq.errors import ChainqError
from chainq.networks import resolve_network
from chainq.tokens import TRON_TOKENS, resolve_token

BINANCE = "TJCo98saj6WND61g1uuKwJ9GMWMT9WkJFo"
BINANCE_HEX = "415a52e96bacdabb82fd05763e25335261b270efcb"
USDT_HEX = "a614f803b6fd780986a42c78ec9c7f77e6ded13c"
CONTROLLER_HEX = "39dd12a54e2bab7c82aa14a1e158b34263d2d510"


def _topic(hex20: str) -> str:
    return hex20.rjust(64, "0")


def test_network():
    net = resolve_network("trx")
    assert (net.key, net.kind, net.chain_id) == ("tron", "tron", 728126428)


def test_hex_roundtrip():
    assert tron.to_hex(BINANCE) == BINANCE_HEX
    assert tron.from_hex(BINANCE_HEX) == BINANCE
    assert tron.from_hex(BINANCE_HEX[2:]) == BINANCE
    assert tron.from_hex(_topic(BINANCE_HEX[2:])) == BINANCE


def test_address_detection():
    assert tron.is_tron_address(BINANCE)
    assert tron.looks_like_tron(BINANCE_HEX)
    assert not tron.is_tron_address(BINANCE[:-1] + "X")
    assert tron.looks_like_tron(BINANCE[:-1] + "X")
    assert not tron.looks_like_tron("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    assert not tron.looks_like_tron("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")


def test_resolve_address_forms():
    assert tron.resolve_tron_address(BINANCE_HEX) == BINANCE
    assert tron.resolve_tron_address("0x" + BINANCE_HEX[2:]) == BINANCE
    with pytest.raises(ChainqError, match="checksum"):
        tron.resolve_tron_address(BINANCE[:-1] + "X")
    with pytest.raises(ChainqError):
        tron.resolve_tron_address("vitalik.eth")


def test_registry_addresses_are_valid():
    for address in TRON_TOKENS.values():
        assert tron.is_tron_address(address)


def test_resolve_token():
    net = resolve_network("tron")
    assert resolve_token("USDT", net) == "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    assert resolve_token(BINANCE_HEX, net) == BINANCE


def test_txid_detection():
    txid = "b2bd6e6316c0f24ecea43d4269ae1e4372928a3ca5d2d9f2d85cb72c828060c8"
    assert tron.is_txid(txid)
    assert tron.is_txid("0x" + txid)
    assert not tron.is_txid("deadbeef")


def test_portfolio_targets_tron():
    assert _resolve_scan_target(BINANCE, None) == (BINANCE, ["tron"])
    assert _resolve_scan_target("0x" + BINANCE_HEX[2:], ["tron"]) == (BINANCE, ["tron"])
    with pytest.raises(ChainqError, match="Tron"):
        _resolve_scan_target(BINANCE, ["ethereum"])


GASFREE_LOGS = [
    {
        "address": USDT_HEX,
        "topics": [
            tron.TRANSFER_TOPIC,
            _topic("3299ed7b187e41cdf537859802d48cf2aa41bf00"),
            _topic("e580e717f6aa318e50fe7b8c4f537fc6a906b0e7"),
        ],
        "data": f"{31_199_000_000:064x}",
    },
    {
        "address": CONTROLLER_HEX,
        "topics": [
            tron.GASFREE_TRANSFER_TOPIC,
            _topic(USDT_HEX),
            _topic("6518550a574808bc185ab20f749daa91605f2c60"),
            _topic("e580e717f6aa318e50fe7b8c4f537fc6a906b0e7"),
        ],
        "data": _topic("76b5c8429b78a38643e5ff9a94b4ca10c1efd867")
        + f"{31_199_000_000:064x}{1_500_000:064x}{1_500_000:064x}{0:064x}",
    },
]


def test_decode_transfers_and_gasfree(monkeypatch):
    monkeypatch.setattr(tron_chain, "_token_meta", lambda token: ("USDT", 6))
    transfers = tron_chain._decode_transfers(GASFREE_LOGS)
    assert transfers == [
        {
            "token": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "symbol": "USDT",
            "amount": 31199.0,
            "from": tron.from_hex("3299ed7b187e41cdf537859802d48cf2aa41bf00"),
            "to": tron.from_hex("e580e717f6aa318e50fe7b8c4f537fc6a906b0e7"),
        }
    ]
    gasfree = tron_chain._decode_gasfree(GASFREE_LOGS)
    assert gasfree["user"] == tron.from_hex("6518550a574808bc185ab20f749daa91605f2c60")
    assert gasfree["provider"] == tron.from_hex("76b5c8429b78a38643e5ff9a94b4ca10c1efd867")
    assert (gasfree["amount"], gasfree["fee"], gasfree["activate_fee"]) == ("31199", "1.5", "1.5")


def test_tx_kind_and_parties():
    assert tron_chain._tx_kind("TransferContract", None, None) == "trx_transfer"
    assert tron_chain._tx_kind("TriggerSmartContract", "transfer(address,uint256)", None) == "trc20_transfer"
    assert tron_chain._tx_kind("TriggerSmartContract", "permitTransfer(...)", {"user": "x"}) == "gasfree_transfer"
    assert tron_chain._tx_kind("TriggerSmartContract", "swap()", None) == "contract_call"
    value = {"owner_address": BINANCE, "to_address": "T2", "amount": 5}
    assert tron_chain._parties("TransferContract", value) == (BINANCE, "T2", 5)
    assert tron_chain._function("a9059cbb" + "0" * 128) == "transfer(address,uint256)"


def test_staked_sun():
    account = {
        "frozenV2": [{"amount": 10}, {"type": "ENERGY", "amount": 5}],
        "delegated_frozenV2_balance_for_bandwidth": 2,
        "account_resource": {"delegated_frozenV2_balance_for_energy": 3},
        "unfrozenV2": [{"unfreeze_amount": 1}],
    }
    assert tron.staked_sun(account) == 21


def test_endpoint_order_prefers_keyless_nodes(monkeypatch):
    monkeypatch.delenv("CHAINQ_RPC_TRON", raising=False)
    monkeypatch.setattr(tron.settings, "trongrid_api_key", None)
    assert tron._urls()[-1] == tron.TRONGRID_URL
    assert tron._headers(tron.TRONGRID_URL) == {}
    monkeypatch.setattr(tron.settings, "trongrid_api_key", "k")
    assert tron._urls()[0] == tron.TRONGRID_URL
    assert tron._headers(tron.TRONGRID_URL) == {"TRON-PRO-API-KEY": "k"}
    assert tron._headers("https://tron-rpc.publicnode.com") == {}


def test_bulk_targets_keep_only_compatible_networks():
    assert _resolve_scan_target(BINANCE, ["tron", "base", "solana"]) == (BINANCE, ["tron"])
