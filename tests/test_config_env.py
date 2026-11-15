import os

import pytest

from chainq import config
from chainq.errors import ChainqError


def test_parse_env_file_handles_quotes_comments_and_export(tmp_path):
    path = tmp_path / ".env"
    path.write_text('# note\nexport COINGECKO_API_KEY="CG-1"\nchainq_rpc_base=https://x # inline\nEMPTY=\nbad line\n')
    assert config.parse_env_file(path) == {
        "COINGECKO_API_KEY": "CG-1",
        "CHAINQ_RPC_BASE": "https://x",
        "EMPTY": "",
    }


def test_later_env_file_wins_and_real_env_wins_over_files(tmp_path, monkeypatch):
    home, local = tmp_path / "home.env", tmp_path / "local.env"
    home.write_text("CHAINQ_TEST_A=home\nCHAINQ_TEST_B=home\n")
    local.write_text("CHAINQ_TEST_A=local\n")
    monkeypatch.setenv("CHAINQ_TEST_B", "shell")
    monkeypatch.delenv("CHAINQ_TEST_A", raising=False)
    config.export_env_files((home, local))
    assert os.environ["CHAINQ_TEST_A"] == "local"
    assert os.environ["CHAINQ_TEST_B"] == "shell"
    monkeypatch.delenv("CHAINQ_TEST_A")


def test_invalid_timeout_is_actionable(monkeypatch):
    monkeypatch.setattr(config, "ENV_FILES", ())
    monkeypatch.setenv("CHAINQ_HTTP_TIMEOUT", "soon")
    with pytest.raises(ChainqError, match="CHAINQ_HTTP_TIMEOUT"):
        config.load_settings()
