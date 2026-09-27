import pytest

from chainq.commands.portfolio import _gather_inputs, _split_addresses
from chainq.errors import ChainqError


def test_split_addresses_handles_lines_commas_and_comments():
    text = "0xA, 0xB\n\n  0xC  # cold wallet\n# skipped\n0xD;0xE"
    assert _split_addresses(text) == ["0xA", "0xB", "0xC", "0xD", "0xE"]


def test_gather_inputs_merges_args_and_file_deduped(tmp_path):
    path = tmp_path / "wallets.txt"
    path.write_text("0xB\n0xC\n")
    assert _gather_inputs(["0xA", "0xB"], str(path)) == ["0xA", "0xB", "0xC"]


def test_gather_inputs_errors():
    with pytest.raises(ChainqError):
        _gather_inputs(None, None)
    with pytest.raises(ChainqError):
        _gather_inputs(None, "/nonexistent/wallets.txt")


def test_paste_without_clipboard_tool_errors(monkeypatch):
    monkeypatch.setattr("chainq.commands.portfolio.shutil.which", lambda _: None)
    with pytest.raises(ChainqError, match="no clipboard tool"):
        _gather_inputs(None, None, paste=True)
