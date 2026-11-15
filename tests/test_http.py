import httpx
import pytest

from chainq import http


def _fake(monkeypatch, responses):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append(url)
        item = responses[len(calls) - 1]
        if isinstance(item, Exception):
            raise item
        return httpx.Response(item[0], headers=item[1] if len(item) > 1 else {})

    monkeypatch.setattr(http.httpx, "request", fake_request)
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    return calls


def test_retries_rate_limit_then_succeeds(monkeypatch):
    calls = _fake(monkeypatch, [(429, {"retry-after": "1"}), (200,)])
    assert http.get("https://x").status_code == 200
    assert len(calls) == 2


def test_returns_last_error_status_after_retries(monkeypatch):
    calls = _fake(monkeypatch, [(503,), (503,), (503,)])
    assert http.get("https://x").status_code == 503
    assert len(calls) == 3


def test_transport_error_raises_after_retries(monkeypatch):
    error = httpx.ConnectError("down")
    _fake(monkeypatch, [error, error, error])
    with pytest.raises(httpx.ConnectError):
        http.get("https://x")


def test_retry_after_is_capped():
    resp = httpx.Response(429, headers={"retry-after": "120"})
    assert http._backoff(0, resp) == http.MAX_RETRY_AFTER_SECONDS
