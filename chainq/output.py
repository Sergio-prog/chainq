import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import dim, fmt_amount

FORMATS = ("text", "json", "table", "toon")

JsonOpt = Annotated[bool, typer.Option("--json", help="structured JSON output (same as --format json)")]
QuietOpt = Annotated[bool, typer.Option("--quiet", "-q", help="bare primary value only (pipe-friendly)")]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="extra detail (sources, endpoints, raw fields)")]
FormatOpt = Annotated[str, typer.Option("--format", "-f", help="output format: text | json | table | toon")]


def dim_label(line: str) -> str:
    if line.lstrip().startswith(("{", "[")):
        return line
    idx = line.find(": ")
    if idx <= 0 or "\033" in line[:idx]:
        return line
    return dim(line[: idx + 1]) + line[idx + 1 :]


def _is_rows(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, dict) for item in value)


def _cell(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return fmt_amount(value)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def render_table(rows: list[dict]) -> str:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    grid = [[_cell(row.get(col)) for col in columns] for row in rows]
    def _is_num(value: object) -> bool:
        return isinstance(value, int | float) and not isinstance(value, bool)

    numeric = [all(_is_num(row.get(col)) for row in rows if row.get(col) is not None) for col in columns]
    widths = [max(len(col), *(len(line[i]) for line in grid)) for i, col in enumerate(columns)]
    def fmt_row(cells: list[str]) -> str:
        return "  ".join(
            cells[i].rjust(widths[i]) if numeric[i] else cells[i].ljust(widths[i]) for i in range(len(columns))
        ).rstrip()
    lines = [fmt_row(list(columns)), "  ".join("-" * w for w in widths)]
    lines.extend(fmt_row(line) for line in grid)
    return "\n".join(lines)


def _tabular(data: object) -> tuple[list[str], list[dict]] | None:
    if _is_rows(data):
        return [], data
    if isinstance(data, dict):
        row_fields = [(k, v) for k, v in data.items() if _is_rows(v)]
        if len(row_fields) == 1:
            prologue = [f"{k}: {_cell(v)}" for k, v in data.items() if not isinstance(v, list | dict)]
            return prologue, row_fields[0][1]
        if all(not isinstance(v, list | dict) for v in data.values()):
            return [], [{"field": k, "value": v} for k, v in data.items()]
    return None


def _toon_scalar(value: object) -> str:
    if isinstance(value, dict | list):
        value = json.dumps(value, default=str)
    if isinstance(value, str):
        if value == "" or value != value.strip() or any(c in value for c in ',\n"'):
            return json.dumps(value)
        return value
    return json.dumps(value, default=str)


def _toon_rows(name: str, items: list[dict], indent: int) -> list[str]:
    fields: list[str] = []
    for item in items:
        for key in item:
            if key not in fields:
                fields.append(key)
    pad = "  " * indent
    lines = [f"{pad}{name}[{len(items)}]{{{','.join(fields)}}}:"]
    lines.extend("  " * (indent + 1) + ",".join(_toon_scalar(item.get(f)) for f in fields) for item in items)
    return lines


def to_toon(data: object) -> str:
    if _is_rows(data):
        return "\n".join(_toon_rows("", data, 0))
    if isinstance(data, dict):
        lines: list[str] = []
        for key, value in data.items():
            if _is_rows(value):
                lines.extend(_toon_rows(key, value, 0))
            elif isinstance(value, list):
                lines.append(f"{key}[{len(value)}]: " + ",".join(_toon_scalar(item) for item in value))
            elif isinstance(value, dict):
                lines.append(f"{key}:")
                lines.extend(f"  {k}: {_toon_scalar(v)}" for k, v in value.items())
            else:
                lines.append(f"{key}: {_toon_scalar(value)}")
        return "\n".join(lines)
    return json.dumps(data, indent=2, default=str)


@dataclass
class Out:
    json: bool = False
    quiet: bool = False
    verbose: bool = False
    format: str = "text"

    def __post_init__(self) -> None:
        if self.format not in FORMATS:
            raise ChainqError(f"unknown format '{self.format}' (use: {' | '.join(FORMATS)})")
        if self.json:
            self.format = "json"

    def emit(
        self,
        data: object,
        text: str | Iterable[str],
        quiet_value: object | None = None,
        verbose_lines: Iterable[str] = (),
    ) -> None:
        if self.format == "json":
            print(json.dumps(data, indent=2, default=str))
            return
        if self.format == "toon":
            print(to_toon(data))
            return
        if self.format == "table":
            tabular = _tabular(data)
            if tabular is None:
                print(json.dumps(data, indent=2, default=str))
                return
            prologue, rows = tabular
            for line in prologue:
                print(line)
            print(render_table(rows))
            return
        if self.quiet and quiet_value is not None:
            print(quiet_value)
            return
        if isinstance(text, str):
            print(dim_label(text))
        else:
            for line in text:
                print(dim_label(line))
        if self.verbose:
            for line in verbose_lines:
                print(dim_label(line))
