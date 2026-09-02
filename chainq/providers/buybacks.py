import html
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import httpx

from chainq import cache, http
from chainq.errors import ChainqError
from chainq.providers import hyperliquid

HYPE_SOURCE_URL = "https://app.hyperliquid.xyz/explorer/address/0xfefefefefefefefefefefefefefefefefefefefe"
LIT_DOCS_URL = "https://docs.lighter.xyz/about-lighter/lit-utility"
UNI_FIREPIT = "0x0D5Cd355e2aBEB8fb1552F56c965B867346d6721"
UNI_TOKEN = "0x1f9840a85d5aF5bf1D1762F925BdADdC4201F984"
UNI_SOURCE_URL = "https://github.com/Uniswap/protocol-fees"
ZRO_SOURCE_URL = "https://layerzero.foundation/zro-buybacks"

UNI_RELEASED_TOPIC = "0x0143172ff1dd87f3691e870b3fb5616db820278d26d2d16c3e03330a240a6c38"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
DEAD_TOPIC = "0x000000000000000000000000000000000000000000000000000000000000dead"
SKY_FLAPPER = "0x374d9c3d5134052bc558f432afa1df6575f07407"
SKY_EXEC_TOPIC = "0xffacc3c568d281ed9c440365e37ddd4f3cc5ce8e5ccac4b1c3b178f10c5531f3"
SKY_SOURCE_URL = "https://etherscan.io/address/0x374d9c3d5134052bc558f432afa1df6575f07407"
RPCS = ("https://rpc.mevblocker.io", "https://gateway.tenderly.co/public/mainnet", "https://eth.drpc.org")
BLOCKS_PER_DAY = 7200

ZRO_SNAPSHOT_AS_OF = "2026-07-21"
ZRO_SNAPSHOT = [
    ("2025-09", 214271, 334821),
    ("2025-10", 346020, 514058),
    ("2025-11", 280622, 370134),
    ("2025-12", 290844, 411034),
    ("2026-01", 216852, 366980),
    ("2026-02", 146430, 277141),
    ("2026-03", 126612, 241538),
    ("2026-04", 143400, 207936),
    ("2026-05", 124574, 143217),
    ("2026-06", 141557, 136980),
]
MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04", "may": "05", "june": "06",
    "july": "07", "august": "08", "september": "09", "october": "10", "november": "11", "december": "12",
}
ZRO_ROW = re.compile(
    r"([\d,]+)\s+ZRO\s+\$([\d,]+)(?:\s+\$[\d,]+)?\s+Stargate\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
    re.IGNORECASE,
)


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _period(name: str, tokens: float, usd: float | None) -> dict:
    return {
        "period": name,
        "tokens": tokens,
        "usd": usd,
        "avg_price_usd": (usd / tokens) if usd and tokens else None,
    }


def _program(**fields) -> dict:
    periods = fields["periods"]
    fields.setdefault("cumulative_tokens", sum(p["tokens"] for p in periods))
    fields.setdefault("cumulative_usd", sum(p["usd"] or 0 for p in periods) or None)
    return fields


def _hype(days: int) -> dict:
    end = int(time.time() * 1000)
    start = end - days * 86_400_000
    key = cache.key_for("buybacks-hype", start // 300_000, days)
    fills = cache.get(key)
    if fills is None:
        fills = hyperliquid.user_fills_by_time(hyperliquid.ASSISTANCE_FUND, start, end)
        cache.put(key, fills, 300)
    buckets: dict[str, dict] = {}
    for fill in fills:
        if fill.get("coin") != hyperliquid.HYPE_SPOT_COIN or fill.get("side") != "B":
            continue
        day = datetime.fromtimestamp(fill["time"] / 1000, UTC).strftime("%Y-%m-%d")
        entry = buckets.setdefault(day, {"tokens": 0.0, "usd": 0.0})
        entry["tokens"] += float(fill["sz"])
        entry["usd"] += float(fill["sz"]) * float(fill["px"])
    periods = [_period(day, values["tokens"], values["usd"]) for day, values in sorted(buckets.items(), reverse=True)]
    return _program(
        program="HYPE",
        asset="HYPE",
        cadence="daily",
        provenance="live",
        source="Hyperliquid Info API (Assistance Fund fills)",
        source_url=HYPE_SOURCE_URL,
        as_of=_today(),
        window_days=days,
        note="spot HYPE buys by the Assistance Fund (0xfefe…fe, coin @107), bucketed per UTC day",
        periods=periods,
    )


def _lit(days: int) -> dict:
    raise ChainqError(
        "LIT buyback per-period data is not publicly retrievable: Lighter's treasury (account 0, "
        "l1 0x0000…0000) buys LIT via daily TWAP but /api/v1/trades auth-gates that account's fills "
        "and /api/v1/recentTrades exposes no history. See " + LIT_DOCS_URL
    )


def _rpc(method: str, params: list) -> object:
    last = ""
    for url in RPCS:
        try:
            resp = http.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, retries=1)
        except httpx.HTTPError as exc:
            last = str(exc)
            continue
        if resp.status_code >= 400:
            last = f"HTTP {resp.status_code}"
            continue
        body = resp.json()
        if body.get("error"):
            last = str(body["error"])
            continue
        return body.get("result")
    raise ChainqError(f"Ethereum RPC failed for {method}: {last}")


def _uint(hex_str: str | None) -> int:
    return int(hex_str, 16) if hex_str else 0


def _is_range_error(exc: ChainqError) -> bool:
    message = str(exc).lower()
    return "range" in message or "too large" in message


def _get_logs(address: str, topics: list, lo: int, hi: int) -> list[dict]:
    try:
        result = _rpc(
            "eth_getLogs",
            [{"address": address, "topics": topics, "fromBlock": hex(lo), "toBlock": hex(hi)}],
        )
        return result or []
    except ChainqError as exc:
        if hi <= lo or not _is_range_error(exc):
            raise
        mid = (lo + hi) // 2
        return _get_logs(address, topics, lo, mid) + _get_logs(address, topics, mid + 1, hi)


def _uni_release_amount(block: int, tx_hash: str) -> float:
    logs = _get_logs(UNI_TOKEN, [TRANSFER_TOPIC, None, DEAD_TOPIC], block, block)
    for log in logs:
        if log.get("transactionHash") == tx_hash:
            return _uint(log.get("data")) / 1e18
    return 0.0


def _block_day(block: int) -> str:
    header = _rpc("eth_getBlockByNumber", [hex(block), False])
    return datetime.fromtimestamp(_uint(header["timestamp"]), UTC).strftime("%Y-%m-%d")


def _scan_logs(address: str, topics: list, days: int) -> list[dict]:
    head = _uint(_rpc("eth_blockNumber", []))
    floor = max(0, head - days * BLOCKS_PER_DAY)
    return _get_logs(address, topics, floor, head)


def _event_days(events: list[dict]) -> list[str]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(lambda event: _block_day(_uint(event["blockNumber"])), events))


def _uni(days: int) -> dict:
    price = _uint(_rpc("eth_call", [{"to": UNI_FIREPIT, "data": "0x42cde4e8"}, "latest"])) / 1e18
    releases_total = _uint(_rpc("eth_call", [{"to": UNI_FIREPIT, "data": "0xaffed0e0"}, "latest"]))
    events = _scan_logs(UNI_FIREPIT, [UNI_RELEASED_TOPIC], days)
    buckets: dict[str, dict] = {}
    blocks = _event_days(events)
    with ThreadPoolExecutor(max_workers=8) as pool:
        amounts = list(pool.map(lambda e: _uni_release_amount(_uint(e["blockNumber"]), e["transactionHash"]), events))
    for day, amount in zip(blocks, amounts, strict=True):
        tokens = amount or price
        entry = buckets.setdefault(day, {"tokens": 0.0, "releases": 0})
        entry["tokens"] += tokens
        entry["releases"] += 1
    periods = [_period(day, values["tokens"], None) for day, values in sorted(buckets.items(), reverse=True)]
    return _program(
        program="UNI",
        asset="UNI",
        cadence="per release",
        provenance="live",
        source="Ethereum onchain (Firepit Released events)",
        source_url=UNI_SOURCE_URL,
        as_of=_today(),
        window_days=days,
        note=f"UNI burned by Firepit (0x0D5C…6721) releases, bucketed per UTC day; {releases_total} "
        f"cumulative releases to date, {price:.0f} UNI burned per release",
        cumulative_tokens=sum(p["tokens"] for p in periods),
        cumulative_usd=None,
        periods=periods,
    )


def _sky(days: int) -> dict:
    events = _scan_logs(SKY_FLAPPER, [SKY_EXEC_TOPIC], days)
    buckets: dict[str, dict] = {}
    for day, event in zip(_event_days(events), events, strict=True):
        data = event["data"][2:]
        entry = buckets.setdefault(day, {"tokens": 0.0, "usd": 0.0, "execs": 0})
        entry["usd"] += int(data[0:64], 16) / 1e18
        entry["tokens"] += int(data[64:128], 16) / 1e18
        entry["execs"] += 1
    periods = [_period(day, values["tokens"], values["usd"]) for day, values in sorted(buckets.items(), reverse=True)]
    return _program(
        program="SKY",
        asset="SKY",
        cadence="per exec (~4h)",
        provenance="live",
        source="Ethereum onchain (Sky Smart Burn Engine Exec events)",
        source_url=SKY_SOURCE_URL,
        as_of=_today(),
        window_days=days,
        note="USDS surplus swapped for SKY by the Smart Burn Engine (0x374d…7407, MCD_FLAP in the Sky "
        "chainlog), bucketed per UTC day",
        periods=periods,
    )


def _parse_zro(raw: str) -> list[tuple[str, int, int]]:
    flat = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))
    rows = []
    for tokens, usd, month, year in ZRO_ROW.findall(flat):
        rows.append((f"{year}-{MONTHS[month.lower()]}", int(tokens.replace(",", "")), int(usd.replace(",", ""))))
    return rows


def _zro_snapshot() -> dict:
    periods = [_period(month, tokens, usd) for month, tokens, usd in reversed(ZRO_SNAPSHOT)]
    return _program(
        program="ZRO",
        asset="ZRO",
        cadence="monthly",
        provenance="snapshot",
        source="LayerZero Foundation buyback tracker",
        source_url=ZRO_SOURCE_URL,
        as_of=ZRO_SNAPSHOT_AS_OF,
        window_days=None,
        note=f"live fetch of layerzero.foundation failed; retained monthly snapshot as of "
        f"{ZRO_SNAPSHOT_AS_OF} (source data only, may be stale) — re-verify at the source URL",
        periods=periods,
    )


def _zro(days: int) -> dict:
    key = cache.key_for("buybacks-zro")
    rows = cache.get(key)
    if rows is None:
        try:
            resp = http.get(ZRO_SOURCE_URL, headers={"user-agent": "Mozilla/5.0"})
            rows = _parse_zro(resp.text) if resp.status_code < 400 else []
        except httpx.HTTPError:
            rows = []
        if rows:
            cache.put(key, rows, 3600)
    if not rows:
        return _zro_snapshot()
    periods = [_period(month, tokens, usd) for month, tokens, usd in sorted(rows, reverse=True)]
    return _program(
        program="ZRO",
        asset="ZRO",
        cadence="monthly",
        provenance="live",
        source="LayerZero Foundation buyback tracker",
        source_url=ZRO_SOURCE_URL,
        as_of=_today(),
        window_days=None,
        note="monthly ZRO buybacks funded by Stargate revenue, parsed live from layerzero.foundation",
        periods=periods,
    )


PROGRAMS = {"hype": _hype, "lit": _lit, "sky": _sky, "uni": _uni, "zro": _zro}
