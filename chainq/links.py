from collections.abc import Callable

from chainq.config import settings
from chainq.errors import ChainqError

LinkBuilder = Callable[[str, str | None], str | None]

PROVIDERS: dict[str, LinkBuilder] = {
    "tradingview": lambda symbol, coin_id: f"https://www.tradingview.com/symbols/{symbol.upper()}USD/",
    "binance": lambda symbol, coin_id: f"https://www.binance.com/en/trade/{symbol.upper()}_USDT",
    "coingecko": lambda symbol, coin_id: f"https://www.coingecko.com/en/coins/{coin_id}" if coin_id else None,
}

DEFAULT_PROVIDERS = ("tradingview",)


def parse_providers(raw: str | None) -> list[str]:
    if raw is None or not raw.strip():
        return list(DEFAULT_PROVIDERS)
    names = [name.strip().lower() for name in raw.split(",") if name.strip()]
    invalid = [name for name in names if name not in PROVIDERS]
    if invalid:
        raise ChainqError(
            f"unknown asset link provider(s): {', '.join(invalid)} (use: {' | '.join(PROVIDERS)})"
        )
    return list(dict.fromkeys(names))


def configured_providers(override: str | None = None) -> list[str]:
    return parse_providers(override if override is not None else settings.asset_links)


def asset_links(symbol: str, coin_id: str | None, providers: list[str]) -> dict[str, str]:
    links: dict[str, str] = {}
    for name in providers:
        url = PROVIDERS[name](symbol, coin_id)
        if url:
            links[name] = url
    return links
