import pytest

from chainq.errors import ChainqError
from chainq.evm_address import checksum, is_hex_address, resolve_address, selector


def test_checksum_matches_eip55():
    assert checksum("0xd8da6bf26964af9d7eed9e03e53415d37aa96045") == "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


def test_is_hex_address_rejects_short_and_non_hex():
    assert not is_hex_address("0x1234")
    assert not is_hex_address("0x" + "g" * 40)
    assert not is_hex_address(None)


def test_resolve_address_rejects_garbage():
    with pytest.raises(ChainqError, match="invalid address"):
        resolve_address("0xzz")


def test_selector_matches_erc20_transfer():
    assert selector("transfer(address,uint256)").hex() == "a9059cbb"
