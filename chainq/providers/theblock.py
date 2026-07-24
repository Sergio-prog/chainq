import json
from datetime import UTC, datetime

import httpx

from chainq import cache, http
from chainq.config import settings
from chainq.errors import ChainqError

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


def flow_history(asset: str) -> list[dict]:
    category, slug = ASSETS[asset]
    key = cache.key_for("theblock-etf", asset)
    rows = cache.get(key)
    if rows is not None:
        return rows
    url = f"https://www.theblock.co/api/charts/chart/crypto-markets/{category}/{slug}"
    try:
        resp = http.get(url, headers={"User-Agent": _UA}, timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise ChainqError(f"The Block request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise ChainqError(f"The Block returned HTTP {resp.status_code} for {asset} ETF flows")
    try:
        series = json.loads(resp.json()["jsonFile"]["data"])["Series"]
    except (KeyError, ValueError) as exc:
        raise ChainqError(f"unexpected The Block response shape for {asset} ETF flows") from exc
    by_day: dict[int, dict] = {}
    for issuer, payload in series.items():
        for point in payload.get("Data") or []:
            timestamp = point.get("Timestamp")
            value = point.get("Result")
            if timestamp is None or value is None:
                continue
            by_day.setdefault(timestamp, {})[issuer] = value
    rows = []
    for timestamp in sorted(by_day, reverse=True):
        issuers = by_day[timestamp]
        rows.append(
            {
                "date": datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d"),
                **{issuer: issuers[issuer] for issuer in sorted(issuers)},
                "net_flow_usd": sum(issuers.values()),
            }
        )
    cache.put(key, rows, 900)
    return rows
