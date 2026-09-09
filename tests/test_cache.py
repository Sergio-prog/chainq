from chainq import cache


def test_put_get_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "cache.json")
    key = cache.key_for("test", {"a": 1})
    assert cache.get(key) is None
    cache.put(key, {"price": 42}, ttl=60)
    assert cache.get(key) == {"price": 42}


def test_expired_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "cache.json")
    key = cache.key_for("stale")
    cache.put(key, "old", ttl=-1)
    assert cache.get(key) is None


def test_expired_entries_pruned_on_put(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "cache.json")
    cache.put(cache.key_for("stale"), "old", ttl=-1)
    cache.put(cache.key_for("fresh"), "new", ttl=60)
    assert cache.key_for("stale") not in cache._load()
    assert cache.get(cache.key_for("fresh")) == "new"


def test_key_is_stable_and_distinct():
    assert cache.key_for("a", {"x": 1}) == cache.key_for("a", {"x": 1})
    assert cache.key_for("a", {"x": 1}) != cache.key_for("a", {"x": 2})


def test_blob_roundtrip_and_age(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "BLOB_DIR", tmp_path / "blobs")
    assert cache.get_blob("list") is None
    cache.put_blob("list", {"tokens": [1, 2]})
    assert cache.get_blob("list", max_age=60) == {"tokens": [1, 2]}
    assert cache.blob_age("list") < 5


def test_blob_stale_read(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "BLOB_DIR", tmp_path / "blobs")
    cache.put_blob("list", "old")
    assert cache.get_blob("list", max_age=-1) is None
    assert cache.get_blob("list") == "old"
    cache.drop_blob("list")
    assert cache.get_blob("list") is None


def test_blob_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "BLOB_DIR", tmp_path / "blobs")
    (tmp_path / "blobs").mkdir()
    (tmp_path / "blobs" / "list.json").write_text("{not json")
    assert cache.get_blob("list") is None
    assert cache.blob_age("list") is None
