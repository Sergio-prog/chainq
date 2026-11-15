import time

import httpx

from chainq.config import settings

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
