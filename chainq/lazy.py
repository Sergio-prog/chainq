import importlib
from functools import cache

import typer
from typer.main import TyperGroup


@cache
def _load(name: str, target: str):
    module_name, _, attr = target.partition(":")
    obj = getattr(importlib.import_module(module_name), attr)
    if isinstance(obj, typer.Typer):
        group = typer.main.get_group(obj)
        group.name = name
        return group
    single = typer.Typer(add_completion=False)
    single.command(name=name)(obj)
    return typer.main.get_command(single)


def lazy_group(commands: dict[str, str]) -> type[TyperGroup]:
    class LazyGroup(TyperGroup):
        def list_commands(self, ctx) -> list[str]:
            return [*super().list_commands(ctx), *commands]

        def get_command(self, ctx, name: str):
            if name in commands:
                return _load(name, commands[name])
            return super().get_command(ctx, name)

    return LazyGroup
