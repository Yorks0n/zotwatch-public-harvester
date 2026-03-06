from __future__ import annotations

import time

import httpx


RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


def get_with_retries(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str],
    attempts: int = 4,
    backoff_seconds: float = 1.0,
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.get(url, params=params)
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < attempts:
                time.sleep(backoff_seconds * attempt)
                continue
            response.raise_for_status()
            return response
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
            last_error = exc
            if attempt >= attempts:
                break
            time.sleep(backoff_seconds * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"request to {url} failed without a response")
