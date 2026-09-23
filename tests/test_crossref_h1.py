from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from src.fetchers.base import FetchWindow
from src.fetchers.crossref import CrossrefFetcher
from src.jobs import harvest_all


START = datetime(2026, 3, 1, tzinfo=UTC)
END = datetime(2026, 3, 2, tzinfo=UTC)


def work(number: int, *, doi: str | None = None) -> dict[str, object]:
    return {"DOI": doi or f"10.1234/{number}", "title": [f"Work {number}"]}


class CrossrefServer:
    def __init__(self, pages: list[list[dict[str, object]] | Exception | httpx.Response], *, final_cursor: bool = True):
        self.pages = pages
        self.final_cursor = final_cursor
        self.requests: list[dict[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        self.requests.append(params)
        page_index = 0 if params["cursor"] == "*" else int(params["cursor"].removeprefix("cursor-"))
        if params["rows"] != "100" or params["mailto"] != "test@example.org":
            raise AssertionError(f"request parameters changed: {params}")
        if params["filter"] != "from-index-date:2026-03-01T00:00:00,until-index-date:2026-03-02T00:00:00":
            raise AssertionError(f"window changed: {params['filter']}")
        if page_index >= len(self.pages):
            raise AssertionError("unexpected Crossref request")
        page = self.pages[page_index]
        if isinstance(page, Exception):
            raise page
        if isinstance(page, httpx.Response):
            return page
        message: dict[str, object] = {"items": page}
        if page_index < len(self.pages) - 1 or self.final_cursor:
            message["next-cursor"] = f"cursor-{page_index + 1}"
        return httpx.Response(200, json={"message": message})


class FakeTable:
    def __init__(self, db: FakeDatabase, name: str):
        self.db = db
        self.name = name
        self.action = ""
        self.payload = None
        self.filters: list[tuple[str, object]] = []

    def select(self, *_args):
        self.action = "select"
        return self

    def insert(self, payload):
        self.action, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.action, self.payload = "update", payload
        return self

    def upsert(self, payload, *, on_conflict):
        self.action, self.payload = "upsert", payload
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def in_(self, key, values):
        self.filters.append((key, set(values)))
        return self

    def limit(self, _value):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self.action == "select":
            if self.name == "works":
                rows = list(self.db.works.values())
            elif self.name == "source_cursors":
                rows = [{"source": "crossref", "cursor_key": "updated_from", "cursor_value": self.db.cursor}]
            else:
                rows = list(self.db.runs)
            for key, value in self.filters:
                rows = [row for row in rows if row.get(key) in value] if isinstance(value, set) else [row for row in rows if row.get(key) == value]
            return SimpleNamespace(data=rows)
        if self.name == "fetch_runs" and self.action == "insert":
            row = {"id": f"run-{len(self.db.runs) + 1}", **self.payload}
            self.db.runs.append(row)
            return SimpleNamespace(data=[row])
        if self.name == "fetch_runs" and self.action == "update":
            for row in self.db.runs:
                if all(row.get(key) in value if isinstance(value, set) else row.get(key) == value for key, value in self.filters):
                    row.update(self.payload)
            return SimpleNamespace(data=[])
        if self.name == "works" and self.action == "upsert":
            for row in self.payload:
                self.db.works[(row["source"], row["source_identifier"])] = row
            return SimpleNamespace(data=[])
        if self.name == "source_cursors" and self.action == "upsert":
            self.db.cursor = self.payload["cursor_value"]
            self.db.cursor_writes += 1
            return SimpleNamespace(data=[])
        raise AssertionError((self.name, self.action))


class FakeDatabase:
    def __init__(self):
        self.works: dict[tuple[str, str], dict[str, object]] = {}
        self.runs: list[dict[str, object]] = []
        self.cursor = START.isoformat().replace("+00:00", "Z")
        self.cursor_writes = 0

    def table(self, name: str) -> FakeTable:
        return FakeTable(self, name)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return END if tz is not None else END.replace(tzinfo=None)


class CrossrefH1Tests(unittest.TestCase):
    def run_window(self, db: FakeDatabase, pages: list[list[dict[str, object]] | Exception | httpx.Response], *, final_cursor: bool = True) -> CrossrefServer:
        server = CrossrefServer(pages, final_cursor=final_cursor)
        real_client = httpx.Client
        with patch.dict(os.environ, {"CROSSREF_MAILTO": "test@example.org"}), patch("src.fetchers.http.time.sleep"), patch.object(
            harvest_all, "datetime", FixedDatetime
        ), patch("src.fetchers.crossref.httpx.Client", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(server), **kwargs)):
            harvest_all._run_crossref_harvest(client=db, fetcher=CrossrefFetcher(), cursor_key="updated_from")
        return server

    def test_more_than_100_and_final_partial_page(self):
        db = FakeDatabase()
        server = self.run_window(db, [[work(i) for i in range(100)], [work(i) for i in range(100, 125)]])
        self.assertEqual([request["cursor"] for request in server.requests], ["*", "cursor-1"])
        self.assertEqual(len(db.works), 125)
        self.assertEqual(db.runs[0]["fetched_count"], 125)
        self.assertEqual(db.runs[0]["status"], "success")
        self.assertEqual(db.cursor_writes, 1)
        self.assertEqual(db.cursor, "2026-03-02T00:00:00Z")

    def test_full_pages_then_empty_page(self):
        db = FakeDatabase()
        server = self.run_window(db, [[work(i) for i in range(100)], [work(i) for i in range(100, 200)], []])
        self.assertEqual([request["cursor"] for request in server.requests], ["*", "cursor-1", "cursor-2"])
        self.assertEqual(len(db.works), 200)
        self.assertEqual(db.runs[0]["fetched_count"], 200)

    def test_full_final_page_without_next_cursor(self):
        db = FakeDatabase()
        server = self.run_window(db, [[work(i) for i in range(100)]], final_cursor=False)
        self.assertEqual(len(server.requests), 1)
        self.assertEqual(db.cursor_writes, 1)

    def test_page_two_failure_and_replay(self):
        db = FakeDatabase()
        before = db.cursor
        with self.assertRaises(httpx.HTTPStatusError):
            self.run_window(db, [[work(i) for i in range(100)], httpx.Response(503)])
        self.assertEqual(len(db.works), 100)
        self.assertEqual(db.runs[0]["status"], "failed")
        self.assertEqual(db.cursor, before)
        self.assertEqual(db.cursor_writes, 0)
        self.run_window(db, [[work(i) for i in range(100)], [work(i) for i in range(100, 120)]])
        self.assertEqual(len(db.works), 120)
        self.assertEqual(db.runs[1]["inserted_count"], 20)
        self.assertEqual(db.runs[1]["updated_count"], 100)
        self.assertEqual(db.cursor_writes, 1)

    def test_timeout_after_multiple_pages_and_replay_with_duplicate_doi(self):
        db = FakeDatabase()
        pages = [[work(i) for i in range(100)], [work(i) for i in range(100, 200)]]
        with self.assertRaises(httpx.ReadTimeout):
            self.run_window(db, pages + [httpx.ReadTimeout("timed out")])
        self.assertEqual(len(db.works), 200)
        self.assertEqual(db.runs[0]["status"], "failed")
        self.assertEqual(db.cursor_writes, 0)
        replay = pages + [[work(200), work(201, doi="HTTPS://DOI.ORG/10.1234/1")]]
        self.run_window(db, replay)
        self.assertEqual(len(db.works), 201)
        self.assertEqual(db.cursor_writes, 1)
        self.assertEqual(db.runs[1]["status"], "success")

    def test_partial_persisted_rows_replay_without_duplicates(self):
        db = FakeDatabase()
        db.works[("crossref", "10.1234/0")] = {"source": "crossref", "source_identifier": "10.1234/0"}
        self.run_window(db, [[work(i) for i in range(120)][:100], [work(i) for i in range(100, 120)]])
        self.assertEqual(len(db.works), 120)
        self.assertEqual(db.runs[0]["inserted_count"], 119)
        self.assertEqual(db.runs[0]["updated_count"], 1)

    def test_process_interruption_stale_run_replays_persisted_rows(self):
        db = FakeDatabase()
        db.runs.append({
            "id": "run-1", "source": "crossref", "status": "running",
            "started_at": "2026-03-01T20:00:00Z", "finished_at": None,
        })
        for i in range(100):
            db.works[("crossref", f"10.1234/{i}")] = {
                "source": "crossref", "source_identifier": f"10.1234/{i}",
            }
        self.run_window(db, [[work(i) for i in range(100)], [work(100)]])
        self.assertEqual(db.runs[0]["status"], "failed")
        self.assertEqual(db.runs[1]["status"], "success")
        self.assertEqual(db.runs[1]["inserted_count"], 1)
        self.assertEqual(len(db.works), 101)
        self.assertEqual(db.cursor_writes, 1)

    def test_public_v1_contract_files_untouched(self):
        # H1 exercises ingestion only; guard the checked-in API definitions.
        from pathlib import Path
        import subprocess

        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["git", "diff", "--quiet", "2a02181d7c87e89bd75cdbb11b4bc9f277bb7c25", "--", "supabase/functions", "supabase/migrations"],
            cwd=root, check=False,
        )
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
