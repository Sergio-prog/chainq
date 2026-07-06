import chainq.update as update
from chainq.update import parse_version


def test_parse_version():
    assert parse_version("1.2.3") == (1, 2, 3)
    assert parse_version("0.2.0") > parse_version("0.1.9")
    assert parse_version("1.0.0") > parse_version("0.9.9")
    assert parse_version("garbage") == (0,)


def test_prerelease_suffix_does_not_crash():
    assert parse_version("1.2.3rc1") == (0,)


def test_upgrade_command_detects_homebrew(monkeypatch):
    monkeypatch.setattr(update.sys, "prefix", "/opt/homebrew/Cellar/chainq/0.11.0/libexec")
    monkeypatch.setattr(update.shutil, "which", lambda name: f"/opt/homebrew/bin/{name}")
    assert update._upgrade_command() == ["brew", "upgrade", "chainq"]


def test_upgrade_command_detects_uv_tool(monkeypatch):
    monkeypatch.setattr(update.sys, "prefix", "/home/u/.local/share/uv/tools/chainq")
    monkeypatch.setattr(update.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert update._upgrade_command() == ["uv", "tool", "upgrade", "chainq"]
