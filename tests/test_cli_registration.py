from typer.testing import CliRunner

from chainq.cli import app

runner = CliRunner()


def _command_names() -> set[str]:
    return {command.name or command.callback.__name__ for command in app.registered_commands}


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
    for name in ("buybacks", "etf", "help"):
        assert name in result.output
