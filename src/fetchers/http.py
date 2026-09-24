from __future__ import annotations

import json
import time

import httpx


RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


class InvalidJsonResponseError(RuntimeError):
    """The upstream returned a successful HTTP response that was not JSON."""


class UpstreamUnavailableError(RuntimeError):
    """A source could not be read after its bounded retry budget."""


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


def get_json_with_retries(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str],
    attempts: int = 4,
    backoff_seconds: float = 1.0,
    context: str = "upstream",
) -> object:
    """Fetch and decode JSON, retrying transient HTTP and malformed-body errors.

    Some upstream gateways return an HTML error page or an empty body with a
    successful status. Treating that as an empty result would silently lose
    source data, so parsing failures are retried and then raised.
    """
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.get(url, params=params)
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < attempts:
                time.sleep(backoff_seconds * attempt)
                continue
            response.raise_for_status()
            try:
                return response.json()
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                last_error = InvalidJsonResponseError(
                    f"{context} returned non-JSON response status={response.status_code} "
                    f"content_type={response.headers.get('content-type', '')!r} "
                    f"bytes={len(response.content)}"
                )
                if attempt >= attempts:
                    raise last_error from exc
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
            last_error = exc
            if attempt >= attempts:
                raise
        if attempt < attempts:
            time.sleep(backoff_seconds * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"request to {url} failed without a response")
