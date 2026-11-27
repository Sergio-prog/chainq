import pytest

from chainq import blocktime
from chainq.blocktime import Header, block_at, parse_when
from chainq.errors import ChainqError

NOW = 1_800_000_000


class FakeProvider:
    def __init__(self, chain, floor=0, pruned=()):
        self.chain = chain
        self.floor = floor
        self.pruned = set(pruned)
        self.calls: list[list[str]] = []
        self.discarded = 0

    @property
    def alive(self):
        return self.discarded < 2

    def discard_active(self):
        self.discarded += 1
        self.pruned.clear()

    def batch(self, headers, blocks):
        tags = [params[0] for _, params in headers]
        self.calls.append(tags)
        return [self._header(tag) for tag in tags]

    def _header(self, tag):
        number = len(self.chain) - 1 if tag == "latest" else int(tag, 16)
        if 0 < number < self.floor:
            return {"error": {"code": -32000, "message": f"EVM is only supported from block {self.floor} onwards"}}
        if number >= len(self.chain) or number in self.pruned:
            return {"result": None}
        return {"result": {"number": hex(number), "timestamp": hex(self.chain[number])}}


class FakeNetwork:
    chain_id = 99999
    name = "Fake"


class FakeClient:
    def __init__(self, provider):
        self.provider = provider
        self.network = FakeNetwork()


@pytest.fixture
def store(monkeypatch):
    blobs: dict = {}
    monkeypatch.setattr(blocktime.cache, "get_blob", lambda name, max_age=None: blobs.get(name))
    monkeypatch.setattr(blocktime.cache, "put_blob", lambda name, value: blobs.__setitem__(name, value))
    monkeypatch.setattr(blocktime.time, "time", lambda: NOW)
    return blobs


def make_chain(length, start=1_600_000_000, pattern=(12, 12, 24, 12, 13)):
    chain = [0, start]
    for i in range(2, length):
        chain.append(chain[-1] + pattern[i % len(pattern)])
    return chain


def expected(chain, target):
    return max(number for number, timestamp in enumerate(chain) if timestamp <= target)


@pytest.mark.parametrize("offset", [0, 1, 7, 11, 12, 13, 1000, 999_999, 3_333_333])
def test_finds_last_block_at_or_before(store, offset):
    chain = make_chain(300_000)
    target = chain[1] + offset
    found = block_at(FakeClient(FakeProvider(chain)), target)
    assert found.block.number == expected(chain, target)
    assert found.next.number == found.block.number + 1
    assert found.next.timestamp > target >= found.block.timestamp


def test_duplicate_timestamps_pick_last_block(store):
    chain = [0] + [1_700_000_000 + i // 4 for i in range(1, 50_000)]
    target = chain[20_001]
    found = block_at(FakeClient(FakeProvider(chain)), target)
    assert found.block.number == expected(chain, target)


def test_target_after_head_returns_latest(store):
    chain = make_chain(5_000)
    found = block_at(FakeClient(FakeProvider(chain)), chain[-1] + 5)
    assert found.block == Header(len(chain) - 1, chain[-1])
    assert found.next is None


def test_future_target_rejected(store):
    with pytest.raises(ChainqError, match="future"):
        block_at(FakeClient(FakeProvider(make_chain(100))), NOW + 3600)


def test_before_first_block_rejected(store):
    chain = make_chain(1_000)
    with pytest.raises(ChainqError, match="before block 1"):
        block_at(FakeClient(FakeProvider(chain)), chain[1] - 10)


def test_floor_hint_moves_search_start(store):
    chain = make_chain(100_000)
    provider = FakeProvider(chain, floor=40_000)
    target = chain[60_000] + 3
    assert block_at(FakeClient(provider), target).block.number == 60_000
    with pytest.raises(ChainqError, match="before block 40,000"):
        block_at(FakeClient(provider), chain[30_000])


def test_pruned_endpoint_is_discarded(store):
    chain = make_chain(10_000)
    provider = FakeProvider(chain, pruned=range(2, 9_000))
    target = chain[4_321]
    assert block_at(FakeClient(provider), target).block.number == 4_321
    assert provider.discarded == 1


def test_repeat_query_hits_cache_only(store):
    chain = make_chain(200_000)
    provider = FakeProvider(chain)
    target = chain[123_456] + 5
    block_at(FakeClient(provider), target)
    rounds_before = len(provider.calls)
    again = block_at(FakeClient(provider), target)
    assert again.block.number == expected(chain, target)
    assert again.rounds == 0
    assert len(provider.calls) == rounds_before


def test_cache_skips_blocks_near_head(store):
    chain = make_chain(50_000)
    block_at(FakeClient(FakeProvider(chain)), chain[-10])
    stored = store[f"blocktime-{FakeNetwork.chain_id}"]["points"]
    assert all(number <= len(chain) - 1 - blocktime.REORG_DEPTH for number, _ in stored)


def test_warm_cache_needs_fewer_rounds(store):
    chain = make_chain(2_000_000)
    provider = FakeProvider(chain)
    cold = block_at(FakeClient(provider), chain[777_777])
    warm = block_at(FakeClient(provider), chain[777_000])
    assert warm.rounds <= cold.rounds
    assert cold.rounds <= 6


def test_closest_prefers_nearer_neighbor():
    found = blocktime.BlockAt(target=100, block=Header(1, 90), next=Header(2, 102), rounds=0, fetched=0, seconds=0)
    assert found.closest == Header(2, 102)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1700000000", 1_700_000_000),
        ("1700000000123", 1_700_000_000),
        ("2024-01-01", 1_704_067_200),
        ("2024-01-01T00:00:00Z", 1_704_067_200),
        ("2024-01-01 02:00:00+02:00", 1_704_067_200),
        ("now", NOW),
        ("3d ago", NOW - 3 * 86400),
        ("-2h", NOW - 7200),
        ("90m", NOW - 5400),
        ("2 weeks ago", NOW - 2 * 604_800),
        ("3mo ago", NOW - 3 * 2_592_000),
    ],
)
def test_parse_when(value, expected):
    assert parse_when(value, now=NOW) == expected


def test_parse_when_rejects_garbage():
    with pytest.raises(ChainqError, match="invalid time"):
        parse_when("next tuesday", now=NOW)
    with pytest.raises(ChainqError, match="invalid time"):
        parse_when("3 fortnights ago", now=NOW)
