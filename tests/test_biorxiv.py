from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

import httpx

from src.fetchers.base import FetchWindow
from src.fetchers.biorxiv import BioRxivFetcher
from src.fetchers.http import UpstreamUnavailableError


WINDOW = FetchWindow(
    start=datetime(2026, 9, 23, tzinfo=UTC),
    end=datetime(2026, 9, 24, tzinfo=UTC),
)


def payload(items: list[dict[str, object]], total: int) -> dict[str, object]:
    return {"collection": items, "messages": [{"total": str(total)}]}


class BiorxivFetcherTests(unittest.TestCase):
    def fetch_with(self, handler):
        transport = httpx.MockTransport(handler)
        real_client = httpx.Client
        with patch(
            "src.fetchers.biorxiv.httpx.Client",
            side_effect=lambda **kwargs: real_client(transport=transport, **kwargs),
        ), patch("src.fetchers.http.time.sleep"):
            return BioRxivFetcher().fetch(WINDOW)

    def test_retries_non_json_response_then_succeeds(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(200, text="<html>temporarily unavailable</html>")
            return httpx.Response(200, json=payload([{"doi": "10.1/a"}], 1))

        rows = self.fetch_with(handler)
        self.assertEqual(rows, [{"doi": "10.1/a"}])
        self.assertEqual(calls, 2)

    def test_page_cursor_uses_details_endpoint_page_size(self):
        requests: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request.url.path)
            if len(requests) == 1:
                return httpx.Response(200, json=payload([{"doi": "10.1/a"}], 31))
            return httpx.Response(200, json=payload([{"doi": "10.1/b"}], 30))

        rows = self.fetch_with(handler)
        self.assertEqual(rows, [{"doi": "10.1/a"}, {"doi": "10.1/b"}])
        self.assertEqual(requests, [
            "/details/biorxiv/2026-09-23/2026-09-24/0/json",
            "/details/biorxiv/2026-09-23/2026-09-24/30/json",
        ])

    def test_non_json_after_retries_has_safe_diagnostics(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>bad gateway</html>")

        with self.assertRaises(UpstreamUnavailableError) as raised:
            self.fetch_with(handler)
        self.assertIn("biorxiv details cursor=0", str(raised.exception))
        self.assertIn("status=200", str(raised.exception))
        self.assertIn("body_prefix='<html>bad gateway</html>'", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
