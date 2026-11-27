import math
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from chainq import cache
from chainq.errors import ChainqError
from chainq.rpc import ChainClient

DENSE_PROBES = 8
COARSE_PROBES = 4
WINDOW = 0.02
SPREAD = 1.0
CURVE = 2
FETCH_ALL = 8
MIN_RADIUS = 8
REORG_DEPTH = 128
MAX_POINTS = 4096
MAX_ROUNDS = 24
FUTURE_SLACK = 120
FLOOR_HINT = re.compile(r"from block (\d+)", re.IGNORECASE)
RELATIVE = re.compile(r"^-?(\d+(?:\.\d+)?)\s*([a-z]+)(?:\s+ago)?$", re.IGNORECASE)
UNIT_SECONDS = {
    **dict.fromkeys(("s", "sec", "secs", "second", "seconds"), 1),
    **dict.fromkeys(("m", "min", "mins", "minute", "minutes"), 60),
    **dict.fromkeys(("h", "hr", "hrs", "hour", "hours"), 3600),
    **dict.fromkeys(("d", "day", "days"), 86400),
    **dict.fromkeys(("w", "wk", "week", "weeks"), 604_800),
    **dict.fromkeys(("mo", "month", "months"), 2_592_000),
    **dict.fromkeys(("y", "yr", "year", "years"), 31_536_000),
}


@dataclass(frozen=True)
class Header:
    number: int
    timestamp: int


@dataclass(frozen=True)
class BlockAt:
    target: int
    block: Header
    next: Header | None
    rounds: int
    fetched: int
    seconds: float

    @property
    def closest(self) -> Header:
        if self.next and self.next.timestamp - self.target < self.target - self.block.timestamp:
            return self.next
        return self.block


def parse_when(value: str, now: float | None = None) -> int:
    text = value.strip()
    now = time.time() if now is None else now
    if text.lower() == "now":
        return int(now)
    if re.fullmatch(r"\d+", text):
        number = int(text)
        return number // 1000 if number >= 10**12 else number
    relative = RELATIVE.match(text)
    if relative and relative.group(2).lower() in UNIT_SECONDS:
        return int(now - float(relative.group(1)) * UNIT_SECONDS[relative.group(2).lower()])
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ChainqError(f"invalid time '{value}': use ISO-8601, Unix seconds, or '<n> <s/m/h/d/w/mo/y> ago'") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def format_time(timestamp: int) -> str:
    return f"{datetime.fromtimestamp(timestamp, tz=UTC):%Y-%m-%d %H:%M:%S} UTC"


def _cache_name(client: ChainClient) -> str:
    return f"blocktime-{client.network.chain_id}"


def _bracket(points: dict[int, int], target: int, floor: int) -> tuple[Header | None, Header | None]:
    lo = hi = None
    for number, timestamp in points.items():
        if number < floor:
            continue
        if timestamp <= target:
            if lo is None or number > lo.number:
                lo = Header(number, timestamp)
        elif hi is None or number < hi.number:
            hi = Header(number, timestamp)
    return lo, hi


def _spread(start: int, stop: int, count: int) -> set[int]:
    if count <= 0 or stop < start:
        return set()
    if stop - start + 1 <= count:
        return set(range(start, stop + 1))
    step = (stop - start) / max(count - 1, 1)
    return {start + round(i * step) for i in range(count)}


def _window(estimate: int, radius: int, low: int, high: int | None) -> list[int]:
    dense_low = max(low, estimate - radius)
    dense_high = estimate + radius if high is None else min(high, estimate + radius)
    refs = {estimate - 1, estimate, estimate + 1} | _spread(dense_low, dense_high, DENSE_PROBES)
    if high is not None:
        refs |= _spread(low, high, COARSE_PROBES + 2) - {low, high}
    return sorted(ref for ref in refs if ref >= low and (high is None or ref <= high))


def _neighbor(points: dict[int, int], anchor: Header, floor: int, direction: int) -> Header | None:
    best = None
    for number, timestamp in points.items():
        if number < floor or (number - anchor.number) * direction <= 0:
            continue
        if (timestamp - anchor.timestamp) * direction <= 0 or timestamp <= 0:
            continue
        if best is None or abs(number - anchor.number) < abs(best.number - anchor.number):
            best = Header(number, timestamp)
    return best


def _slope(a: Header, b: Header) -> float:
    return (b.number - a.number) / (b.timestamp - a.timestamp)


def _tangent(left: float, left_width: float, right: float, right_width: float) -> float:
    if left <= 0 or right <= 0:
        return 0.0
    w1 = 2 * right_width + left_width
    w2 = right_width + 2 * left_width
    return (w1 + w2) / (w1 / left + w2 / right)


def _interpolate(points: dict[int, int], lo: Header, hi: Header, target: int, floor: int) -> tuple[int, int]:
    width = hi.timestamp - lo.timestamp
    slope = _slope(lo, hi)
    before = _neighbor(points, lo, floor, -1)
    after = _neighbor(points, hi, floor, 1)
    left = _tangent(_slope(before, lo), lo.timestamp - before.timestamp, slope, width) if before else slope
    right = _tangent(slope, width, _slope(hi, after), after.timestamp - hi.timestamp) if after else slope
    t = (target - lo.timestamp) / width
    cubic = (
        (2 * t**3 - 3 * t**2 + 1) * lo.number
        + (t**3 - 2 * t**2 + t) * width * left
        + (-2 * t**3 + 3 * t**2) * hi.number
        + (t**3 - t**2) * width * right
    )
    linear = lo.number + (target - lo.timestamp) * slope
    return round(cubic), math.ceil(abs(cubic - linear))


def _probes(points: dict[int, int], lo: Header | None, hi: Header | None, target: int, floor: int) -> list[int]:
    if lo and hi:
        gap = hi.number - lo.number
        if gap - 1 <= FETCH_ALL:
            return list(range(lo.number + 1, hi.number))
        estimate, doubt = _interpolate(points, lo, hi, target, floor)
        radius = max(MIN_RADIUS, math.ceil(SPREAD * math.sqrt(gap)), CURVE * doubt)
        return _window(estimate, radius, lo.number + 1, hi.number - 1)
    if lo:
        below = _neighbor(points, lo, floor, -1)
        if below is None:
            return []
        rate = (lo.number - below.number) / (lo.timestamp - below.timestamp)
        gap = max(round((target - lo.timestamp) * rate), 1)
        radius = max(MIN_RADIUS, math.ceil(SPREAD * math.sqrt(gap)), math.ceil(gap * WINDOW))
        return _window(lo.number + gap, radius, lo.number + 1, None)
    return []


def _fetch(client: ChainClient, refs: list[int | str]) -> list[dict]:
    tags = [ref if isinstance(ref, str) else hex(ref) for ref in refs]
    return client.provider.batch(
        [("eth_getHeaderByNumber", [tag]) for tag in tags],
        [("eth_getBlockByNumber", [tag, False]) for tag in tags],
    )


def _remember(name: str, points: dict[int, int], fresh: dict[int, int], ceiling: float, floor: int) -> None:
    unsafe = {number for number in fresh if number > ceiling}
    merged = sorted((number, timestamp) for number, timestamp in points.items() if number not in unsafe)
    while len(merged) > MAX_POINTS:
        merged = merged[:2] + merged[2:-1:2] + merged[-1:]
    cache.put_blob(name, {"floor": floor, "points": merged})


def block_at(client: ChainClient, target: int) -> BlockAt:
    started = time.perf_counter()
    if target > time.time() + FUTURE_SLACK:
        raise ChainqError(f"{format_time(target)} is in the future")
    name = _cache_name(client)
    stored = cache.get_blob(name) or {}
    floor = int(stored.get("floor", 0))
    points: dict[int, int] = {int(number): int(timestamp) for number, timestamp in stored.get("points", [])}
    fresh: dict[int, int] = {}
    latest: Header | None = None
    rounds = fetched = 0
    while True:
        lo, hi = _bracket(points, target, floor)
        if latest and target >= latest.timestamp:
            lo, hi = latest, None
            break
        if lo and hi and hi.number - lo.number == 1:
            break
        if lo is None and floor in points:
            raise ChainqError(f"{format_time(target)} is before block {floor:,} ({format_time(points[floor])})")
        if rounds >= MAX_ROUNDS:
            raise ChainqError("block search did not converge")
        refs: list[int | str] = []
        if hi is None and latest is None:
            refs.append("latest")
        if lo is None:
            refs += [floor, floor + 1]
        refs += [ref for ref in _probes(points, lo, hi, target, floor) if ref not in refs]
        responses = _fetch(client, refs)
        rounds += 1
        fetched += len(refs)
        missing: list[int] = []
        for ref, response in zip(refs, responses, strict=True):
            if "error" in response:
                message = str(response["error"].get("message", response["error"]))
                hint = FLOOR_HINT.search(message)
                if hint and int(hint.group(1)) > floor:
                    floor = int(hint.group(1))
                    continue
                raise ChainqError(f"eth_getBlockByNumber({ref}) failed: {message}")
            result = response.get("result")
            if result is None:
                if ref == "latest":
                    raise ChainqError("RPC returned no latest block")
                if latest is None or ref <= latest.number:
                    missing.append(ref)
                continue
            header = Header(int(result["number"], 16), int(result["timestamp"], 16))
            points[header.number] = header.timestamp
            fresh[header.number] = header.timestamp
            if ref == "latest":
                latest = header
        if missing:
            client.provider.discard_active()
            if not client.provider.alive:
                raise ChainqError(f"no {client.network.name} RPC endpoint serves block {missing[0]:,}")
    if lo.timestamp == 0 and hi:
        raise ChainqError(f"{format_time(target)} is before block {hi.number:,} ({format_time(hi.timestamp)})")
    if fresh or floor != stored.get("floor", 0):
        _remember(name, points, fresh, latest.number - REORG_DEPTH if latest else math.inf, floor)
    return BlockAt(target, lo, hi, rounds, fetched, time.perf_counter() - started)
