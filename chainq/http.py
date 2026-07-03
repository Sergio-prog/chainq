import time

import httpx

from chainq.config import settings


def request(method: str, url: str, *, retries: int = 2, **kwargs) -> httpx.Response:
    kwargs.setdefault("timeout", settings.http_timeout)
    last_exc: httpx.HTTPError | None = None
    for attempt in range(retries + 1):
        try:
            resp = httpx.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt == retries:
                raise
            time.sleep(0.5 * 2**attempt)
            continue
        if resp.status_code >= 500 and attempt < retries:
            time.sleep(0.5 * 2**attempt)
            continue
        return resp
    raise last_exc


def get(url: str, **kwargs) -> httpx.Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs) -> httpx.Response:
    return request("POST", url, **kwargs)
