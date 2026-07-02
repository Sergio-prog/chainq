import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Annotated

import typer

JsonOpt = Annotated[bool, typer.Option("--json", help="structured JSON output for machine parsing")]
QuietOpt = Annotated[bool, typer.Option("--quiet", "-q", help="bare primary value only (pipe-friendly)")]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="extra detail (sources, endpoints, raw fields)")]


@dataclass
class Out:
    json: bool = False
    quiet: bool = False
    verbose: bool = False

    def emit(
        self,
        data: object,
        text: str | Iterable[str],
        quiet_value: object | None = None,
        verbose_lines: Iterable[str] = (),
    ) -> None:
        if self.json:
            print(json.dumps(data, indent=2, default=str))
            return
        if self.quiet and quiet_value is not None:
            print(quiet_value)
            return
        if isinstance(text, str):
            print(text)
        else:
            for line in text:
                print(line)
        if self.verbose:
            for line in verbose_lines:
                print(line)
