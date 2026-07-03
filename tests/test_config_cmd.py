import pytest

from chainq.commands import config
from chainq.errors import ChainqError


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / ".env")


def test_set_get_roundtrip(capsys):
    config.set_("coingecko-api-key", "CG-abcdef123456")
    assert config._read() == {"COINGECKO_API_KEY": "CG-abcdef123456"}
    config.get("COINGECKO_API_KEY")
    assert capsys.readouterr().out.strip().endswith("CG-abcdef123456")


def test_set_masks_secret_in_output(capsys):
    config.set_("opensea_api_key", "fc250a492ebb3daf")
    out = capsys.readouterr().out
    assert "fc250a492ebb3daf" not in out
    assert "fc25…3daf" in out


def test_unset_removes_key():
    config.set_("CHAINQ_RPC_ETHEREUM", "https://example.com")
    config.unset("chainq-rpc-ethereum")
    assert config._read() == {}


def test_get_missing_raises():
    with pytest.raises(ChainqError):
        config.get("NOPE")


def test_file_permissions():
    config.set_("COINGECKO_API_KEY", "x")
    assert (config.CONFIG_PATH.stat().st_mode & 0o777) == 0o600
