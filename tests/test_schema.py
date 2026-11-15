import json

from typer.testing import CliRunner

from chainq.cli import app

runner = CliRunner()


def _schema(*args: str) -> dict:
    result = runner.invoke(app, ["schema", *args, "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_schema_lists_every_leaf_command():
    names = {c["command"] for c in _schema()["commands"]}
    assert {"price", "portfolio", "protocols hl funding", "evm keccak", "tokens search", "schema"} <= names


def test_schema_subtree_and_option_details():
    commands = _schema("protocols", "hl")["commands"]
    assert all(c["command"].startswith("protocols hl ") for c in commands)
    funding = next(c for c in commands if c["command"] == "protocols hl funding")
    assert funding["contract_flags"] is True
    history = next(o for o in funding["options"] if o["name"] == "--history")
    assert history["type"] == "flag" and history["short"] == "-H"
    assert not any(o["name"] in ("--json", "--format", "--help") for o in funding["options"])


def test_schema_unknown_path_is_actionable():
    result = runner.invoke(app, ["schema", "protocols", "nope"])
    assert result.exit_code == 1
    assert "see `chainq schema protocols`" in str(result.exception)
