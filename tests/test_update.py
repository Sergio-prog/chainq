from subprocess import CompletedProcess

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
    assert update._upgrade_command() == ["brew", "upgrade", "--no-ask", "chainq"]


def test_upgrade_command_detects_uv_tool(monkeypatch):
    monkeypatch.setattr(update.sys, "prefix", "/home/u/.local/share/uv/tools/chainq")
    monkeypatch.setattr(update.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert update._upgrade_command() == ["uv", "tool", "upgrade", "chainq"]


def test_update_captures_package_manager_output(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(update, "fetch_latest_version", lambda: "9.0.0")
    monkeypatch.setattr(update, "_write_state", lambda state: None)
    monkeypatch.setattr(update, "_read_state", lambda: {})
    monkeypatch.setattr(update, "_upgrade_command", lambda: ["brew", "upgrade", "--no-ask", "chainq"])

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return CompletedProcess(cmd, 0, stdout="noisy output", stderr="")

    monkeypatch.setattr(update.subprocess, "run", run)

    update.update(False, False)

    assert calls == [
        (["brew", "upgrade", "--no-ask", "chainq"], {"capture_output": True, "text": True})
    ]
    assert capsys.readouterr().out == "Updating chainq... done (9.0.0)\n"


def test_update_verbose_streams_package_manager_output(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(update, "fetch_latest_version", lambda: "9.0.0")
    monkeypatch.setattr(update, "_write_state", lambda state: None)
    monkeypatch.setattr(update, "_read_state", lambda: {})
    monkeypatch.setattr(update, "_upgrade_command", lambda: ["uv", "tool", "upgrade", "chainq"])

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return CompletedProcess(cmd, 0)

    monkeypatch.setattr(update.subprocess, "run", run)

    update.update(False, True)

    assert calls == [(["uv", "tool", "upgrade", "chainq"], {})]
    assert capsys.readouterr().out == (
        "running: uv tool upgrade chainq\n"
        "chainq updated to 9.0.0\n"
    )


def test_force_reinstall_homebrew_is_non_interactive(monkeypatch):
    calls = []
    monkeypatch.setattr(update, "fetch_latest_version", lambda: "9.0.0")
    monkeypatch.setattr(update, "_write_state", lambda state: None)
    monkeypatch.setattr(update, "_read_state", lambda: {})
    monkeypatch.setattr(update, "_upgrade_command", lambda: ["brew", "upgrade", "--no-ask", "chainq"])
    monkeypatch.setattr(
        update.subprocess,
        "run",
        lambda cmd, **kwargs: calls.append(cmd) or CompletedProcess(cmd, 0, stdout="", stderr=""),
    )

    update.update(True, False)

    assert calls == [["brew", "reinstall", "--no-ask", "chainq"]]
