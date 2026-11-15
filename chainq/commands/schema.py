from typing import Annotated

import typer

from chainq import __version__
from chainq.errors import ChainqError
from chainq.fmt import dim
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt

CONTRACT_OPTIONS = ("--json", "--quiet", "--verbose", "--format")
HIDDEN_OPTIONS = ("--help", "--install-completion", "--show-completion")
SCALARS = (str, int, float, bool)


def _default(value: object) -> object:
    if isinstance(value, SCALARS):
        return value
    if isinstance(value, list | tuple) and all(isinstance(item, SCALARS) for item in value):
        return list(value) or None
    return None


def _describe_param(param) -> dict:
    choices = getattr(param.type, "choices", None)
    entry = {
        "name": param.name if param.param_type_name == "argument" else max(param.opts, key=len),
        "short": next((opt for opt in param.opts if len(opt) == 2), None),
        "type": "flag" if getattr(param, "is_flag", False) else param.type.name,
        "required": param.required or None,
        "multiple": (param.multiple or param.nargs == -1) or None,
        "default": None if getattr(param, "is_flag", False) else _default(param.default),
        "choices": list(choices) if choices else None,
        "help": getattr(param, "help", None),
    }
    return {key: value for key, value in entry.items() if value is not None}


def _usage(path: list[str], params: list[dict], arguments: list[dict]) -> str:
    parts = ["chainq", *path]
    for arg in arguments:
        name = arg["name"].upper() + ("..." if arg.get("multiple") else "")
        parts.append(name if arg.get("required") else f"[{name}]")
    for opt in params:
        flag = opt["name"]
        value = "" if opt["type"] == "flag" else " " + ("|".join(opt["choices"]) if "choices" in opt else opt["type"].upper())
        parts.append(f"[{flag}{value}]")
    return " ".join(parts)


def _describe(path: list[str], command) -> dict:
    params = [p for p in command.params if not p.hidden]
    arguments = [_describe_param(p) for p in params if p.param_type_name == "argument"]
    options = [
        _describe_param(p)
        for p in params
        if p.param_type_name == "option" and not set(p.opts) & {*CONTRACT_OPTIONS, *HIDDEN_OPTIONS}
    ]
    entry = {
        "command": " ".join(path),
        "help": command.get_short_help_str(limit=200),
        "usage": _usage(path, options, arguments),
        "contract_flags": any("--json" in p.opts for p in params) or None,
        "arguments": arguments or None,
        "options": options or None,
    }
    return {key: value for key, value in entry.items() if value is not None}


def _walk(command, ctx, path: list[str]):
    if not hasattr(command, "list_commands"):
        yield _describe(path, command)
        return
    for name in command.list_commands(ctx):
        sub = command.get_command(ctx, name)
        if sub is not None and not sub.hidden:
            yield from _walk(sub, ctx, [*path, name])


def _select(root, ctx, path: list[str]):
    command = root
    for depth, name in enumerate(path):
        sub = command.get_command(ctx, name) if hasattr(command, "list_commands") else None
        if sub is None:
            parent = " ".join(["chainq schema", *path[:depth]])
            raise ChainqError(f"unknown command '{' '.join(path[: depth + 1])}' (see `{parent}`)")
        command = sub
    return command


def schema(
    ctx: typer.Context,
    path: Annotated[
        list[str] | None, typer.Argument(help="command path to describe, e.g. `protocols hl`; default: everything")
    ] = None,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Machine-readable listing of every command, argument, and option (for agents and tooling)."""
    out = Out(json_out, quiet, verbose, format)
    root = ctx.find_root().command
    target = _select(root, ctx, path or [])
    commands = list(_walk(target, ctx, path or []))
    data = {
        "version": __version__,
        "contract_flags": "--json | -q/--quiet | -v/--verbose | -f/--format text|json|table|toon",
        "commands": commands,
    }
    lines = [dim("commands marked * also take --json, -q, -v, -f text|json|table|toon")]
    lines += [f"{c['usage']}{' *' if c.get('contract_flags') else ''}  {dim(c['help'])}" for c in commands]
    out.emit(data, lines, quiet_value="\n".join(c["command"] for c in commands))
