import time

import httpx

from chainq.config import settings
from chainq.errors import ChainqError

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_AFTER_SECONDS = 3.0


def _backoff(attempt: int, resp: httpx.Response | None = None) -> float:
    retry_after = resp.headers.get("retry-after") if resp is not None else None
    if retry_after and retry_after.isdigit():
        return min(float(retry_after), MAX_RETRY_AFTER_SECONDS)
    return 0.5 * 2**attempt


def request(method: str, url: str, *, retries: int = 2, **kwargs) -> httpx.Response:
    kwargs.setdefault("timeout", settings.http_timeout)
    for attempt in range(retries):
        try:
            resp = httpx.request(method, url, **kwargs)
        except httpx.HTTPError:
            time.sleep(_backoff(attempt))
            continue
        if resp.status_code not in RETRY_STATUSES:
            return resp
        time.sleep(_backoff(attempt, resp))
    return httpx.request(method, url, **kwargs)


def get(url: str, **kwargs) -> httpx.Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs) -> httpx.Response:
    return request("POST", url, **kwargs)


class UpstreamError(ChainqError):
    def __init__(self, message: str, status: int | None = None, response: httpx.Response | None = None):
        super().__init__(message)
        self.status = status
        self.response = response


def fetch_json(source: str, url: str, *, method: str = "GET", missing_ok: bool = False, **kwargs) -> object:
    try:
        resp = request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise UpstreamError(f"{source} request failed: {exc}") from exc
    if resp.status_code == 404 and missing_ok:
        return None
    if resp.status_code == 429:
        raise UpstreamError(f"{source} rate limit hit; retry shortly", 429, resp)
    if resp.status_code >= 400:
        raise UpstreamError(f"{source} returned HTTP {resp.status_code}", resp.status_code, resp)
    try:
        return resp.json()
    except ValueError as exc:
        raise UpstreamError(f"{source} returned invalid JSON", resp.status_code, resp) from exc


def fetch_graphql(source: str, url: str, query: str) -> dict:
    payload = fetch_json(source, url, method="POST", json={"query": query})
    errors = payload.get("errors") if isinstance(payload, dict) else None
    if errors:
        raise UpstreamError(f"{source} error: {errors[0].get('message', errors)}")
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise UpstreamError(f"{source} returned an unexpected payload (no data)")
    return data
