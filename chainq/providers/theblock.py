import json
from datetime import UTC, datetime

from chainq import cache, http
from chainq.errors import ChainqError
from chainq.http import UpstreamError

ASSETS = {
    "BTC": ("bitcoin-etf", "spot-bitcoin-etf-flows"),
    "ETH": ("ethereum-etf", "spot-ethereum-etf-flows"),
}
SITE = {
    "BTC": "https://www.theblock.co/data/etfs/bitcoin-etf/spot-bitcoin-etf-flows",
    "ETH": "https://www.theblock.co/data/etfs/ethereum-etf/spot-ethereum-etf-flows",
}
SOURCE = "The Block"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def _fetch_flow_history(asset: str) -> list[dict]:
    category, slug = ASSETS[asset]
    url = f"https://www.theblock.co/api/charts/chart/crypto-markets/{category}/{slug}"
    try:
        payload = http.fetch_json("The Block", url, headers={"User-Agent": _UA})
    except UpstreamError as exc:
        raise ChainqError(f"{exc} for {asset} ETF flows") from exc
    try:
        series = json.loads(payload["jsonFile"]["data"])["Series"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ChainqError(f"unexpected The Block response shape for {asset} ETF flows") from exc
    by_day: dict[int, dict] = {}
    for issuer, points in series.items():
        for point in points.get("Data") or []:
            timestamp = point.get("Timestamp")
            value = point.get("Result")
            if timestamp is None or value is None:
                continue
            by_day.setdefault(timestamp, {})[issuer] = value
    return [
        {
            "date": datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d"),
            **{issuer: by_day[timestamp][issuer] for issuer in sorted(by_day[timestamp])},
            "net_flow_usd": sum(by_day[timestamp].values()),
        }
        for timestamp in sorted(by_day, reverse=True)
    ]


def flow_history(asset: str) -> list[dict]:
    return cache.remember(("theblock-etf", asset), 900, lambda: _fetch_flow_history(asset))
