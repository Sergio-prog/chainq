import subprocess
import sys

import pytest
import typer
from typer.testing import CliRunner

from chainq.cli import app

runner = CliRunner()


def _command_names() -> set[str]:
    group = typer.main.get_command(app)
    return set(group.list_commands(typer.Context(group)))


def test_new_top_level_commands_registered():
    names = _command_names()
    assert {"buybacks", "etf", "help"} <= names


def test_help_command_matches_root_help():
    root = runner.invoke(app, ["--help"])
    via_command = runner.invoke(app, ["help"])
    assert root.exit_code == 0
    assert via_command.exit_code == 0
    assert via_command.output == root.output


def test_help_lists_new_commands():
    result = runner.invoke(app, ["--help"])
    for name in ("buybacks", "etf", "help", "tokens"):
        assert name in result.output


def test_tokens_group_registered():
    result = runner.invoke(app, ["tokens", "--help"])
    assert result.exit_code == 0
    for name in ("search", "refresh", "status"):
        assert name in result.output


def test_every_lazy_command_loads():
    group = typer.main.get_command(app)
    ctx = typer.Context(group)
    for name in group.list_commands(ctx):
        assert group.get_command(ctx, name) is not None, name


def test_startup_does_not_import_heavy_deps():
    probe = "import sys, chainq.cli; print(sorted(m for m in ('web3', 'pydantic', 'rich.console') if m in sys.modules))"
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]"


def test_unexpected_errors_are_one_line(monkeypatch, capsys):
    from chainq import cli, update

    def boom():
        raise KeyError("data")

    monkeypatch.setattr(cli, "app", boom)
    monkeypatch.setattr(update, "maybe_remind", lambda: None)
    monkeypatch.setattr(cli.sys, "argv", ["chainq", "price", "btc"])
    monkeypatch.delenv("CHAINQ_DEBUG", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        cli.run()
    assert exit_info.value.code == 1
    err = capsys.readouterr().err
    assert err.startswith("error: unexpected KeyError") and err.count("\n") == 1
