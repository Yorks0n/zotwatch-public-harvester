from __future__ import annotations

import unittest
from unittest.mock import patch

from src.fetchers.http import UpstreamUnavailableError
from typer.testing import CliRunner

from src.main import app
from src.jobs import harvest_all
from src.jobs import cleanup
import test_crossref_h1 as h1


class MultiSourceTable(h1.FakeTable):
    def execute(self):
        if self.name == "source_cursors":
            if self.action == "upsert":
                self.db.cursors[(self.payload["source"], self.payload["cursor_key"])] = self.payload["cursor_value"]
                return type("Response", (), {"data": []})()
            rows = [
                {"source": source, "cursor_key": key, "cursor_value": value}
                for (source, key), value in self.db.cursors.items()
            ]
            for key, value in self.filters:
                rows = [row for row in rows if row[key] == value]
            return type("Response", (), {"data": rows})()
        return super().execute()


class MultiSourceDatabase(h1.FakeDatabase):
    def __init__(self):
        super().__init__()
        self.cursors = {("crossref", "updated_from"): self.cursor}

    def table(self, name):
        return MultiSourceTable(self, name)


class H2Tests(unittest.TestCase):
    def invoke(self, enabled, failures=(), cleanup_error=None):
        attempted = []
        db = object()

        def run_source(*, fetcher, **_kwargs):
            attempted.append(fetcher.source_name)
            if fetcher.source_name in failures:
                if fetcher.source_name == "biorxiv":
                    raise UpstreamUnavailableError("biorxiv unavailable")
                raise RuntimeError("private upstream detail")

        def cleanup(*, client):
            self.assertIs(client, db)
            if cleanup_error:
                raise RuntimeError("private cleanup detail")

        with patch.object(harvest_all, "get_supabase_client", return_value=db), patch.object(
            harvest_all, "fetch_enabled_sources", return_value=[{"id": name} for name in enabled]
        ), patch.object(harvest_all, "_run_crossref_harvest", side_effect=run_source), patch.object(
            harvest_all, "_run_arxiv_harvest", side_effect=run_source
        ), patch.object(harvest_all, "_run_biorxiv_family_harvest", side_effect=run_source), patch.object(
            harvest_all, "run_cleanup", side_effect=cleanup
        ):
            result = harvest_all.run_harvest_all()
        return result, attempted

    def test_all_enabled_succeed_and_disabled_paused_skipped(self):
        result, attempted = self.invoke(["crossref", "arxiv", "openalex"])
        self.assertEqual(result.status, "success")
        self.assertEqual(attempted, ["crossref", "arxiv"])
        self.assertEqual(result.skipped, ("biorxiv", "medrxiv", "openalex"))

    def test_failure_does_not_stop_later_sources(self):
        result, attempted = self.invoke(["crossref", "arxiv", "biorxiv"], failures={"crossref"})
        self.assertEqual(result.status, "partial_failed")
        self.assertEqual(result.failed, ("crossref",))
        self.assertEqual(result.succeeded, ("arxiv", "biorxiv"))
        self.assertEqual(attempted, ["crossref", "arxiv", "biorxiv"])

    def test_optional_preprint_source_failure_is_warning_and_does_not_fail_run(self):
        result, attempted = self.invoke(["crossref", "biorxiv", "arxiv"], failures={"biorxiv"})
        self.assertEqual(result.status, "success")
        self.assertEqual(result.failed, ())
        self.assertEqual(result.skipped, ("biorxiv",))
        self.assertEqual(attempted, ["crossref", "biorxiv", "arxiv"])

    def test_all_fail_and_zero_attempts_fail(self):
        result, attempted = self.invoke(["crossref", "arxiv"], failures={"crossref", "arxiv"})
        self.assertEqual(result.status, "failed")
        self.assertEqual(attempted, ["crossref", "arxiv"])
        self.assertEqual(self.invoke([])[0].status, "failed")

    def test_cleanup_failure_is_separate(self):
        result, attempted = self.invoke(["crossref", "arxiv"], failures={"crossref"}, cleanup_error=True)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failed, ("crossref",))
        self.assertEqual(result.succeeded, ("arxiv",))
        self.assertEqual(result.cleanup_error, "RuntimeError")
        self.assertEqual(attempted, ["crossref", "arxiv"])

    def test_orchestration_failure(self):
        with patch.object(harvest_all, "get_supabase_client", side_effect=RuntimeError("secret")):
            result = harvest_all.run_harvest_all()
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.orchestration_error, "RuntimeError")

    def test_cli_exit_codes_and_workflow_command(self):
        from pathlib import Path

        runner = CliRunner()
        for status, expected in (("success", 0), ("partial_failed", 1), ("failed", 1)):
            with patch("src.main.run_harvest_all", return_value=harvest_all.HarvestResult(status=status)):
                self.assertEqual(runner.invoke(app, ["harvest-all"]).exit_code, expected)
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/harvest.yml").read_text()
        self.assertIn("run: python -m src.main harvest-all", workflow)
        self.assertNotIn("continue-on-error", workflow)

    def test_crossref_partial_failure_keeps_counts_and_cursor(self):
        db = h1.FakeDatabase()
        before = db.cursor
        with self.assertRaises(RuntimeError):
            with patch.object(harvest_all, "upsert_works", side_effect=RuntimeError("private persistence detail")):
                h1.CrossrefH1Tests().run_window(db, [h1.work(i) for i in range(100)])
        self.assertEqual(db.runs[0]["status"], "failed")
        self.assertEqual(db.runs[0]["fetched_count"], 100)
        self.assertEqual(db.runs[0]["inserted_count"], 0)
        self.assertEqual(db.runs[0]["error_summary"], "RuntimeError")
        self.assertEqual(db.cursor, before)

    def test_crossref_failure_and_successful_sibling_keep_independent_runs_and_cursors(self):
        db = MultiSourceDatabase()
        original_cursor = db.cursors[("crossref", "updated_from")]

        with patch.object(harvest_all, "get_supabase_client", return_value=db), patch.object(
            harvest_all, "fetch_enabled_sources", return_value=[{"id": "crossref"}, {"id": "arxiv"}]
        ), patch.object(harvest_all, "datetime", h1.FixedDatetime), patch.object(
            harvest_all.CrossrefFetcher, "fetch", side_effect=RuntimeError("private upstream detail")
        ), patch.object(harvest_all.ArxivFetcher, "fetch", return_value=[]), patch.object(
            harvest_all, "run_cleanup"
        ):
            result = harvest_all.run_harvest_all()
        self.assertEqual(result.status, "partial_failed")
        self.assertEqual([(run["source"], run["status"]) for run in db.runs],
                         [("crossref", "failed"), ("arxiv", "success")])
        self.assertEqual(db.runs[0]["error_summary"], "RuntimeError")
        self.assertEqual(db.runs[0]["inserted_count"], 0)
        self.assertEqual(db.cursors[("crossref", "updated_from")], original_cursor)
        self.assertEqual(db.cursors[("arxiv", "updated_from")], "2026-03-02T00:00:00Z")

    def test_cleanup_failure_does_not_rewrite_successful_source_run(self):
        db = MultiSourceDatabase()
        with patch.object(harvest_all, "get_supabase_client", return_value=db), patch.object(
            harvest_all, "fetch_enabled_sources", return_value=[{"id": "arxiv"}]
        ), patch.object(harvest_all, "datetime", h1.FixedDatetime), patch.object(
            harvest_all.ArxivFetcher, "fetch", return_value=[]
        ), patch.object(harvest_all, "run_cleanup", side_effect=RuntimeError("private cleanup detail")):
            result = harvest_all.run_harvest_all()
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.cleanup_error, "RuntimeError")
        self.assertEqual([(row["source"], row["status"]) for row in db.runs], [("arxiv", "success")])

    def test_cleanup_preserves_last_successful_window(self):
        class Query:
            def __init__(self, table):
                self.table = table
                self.filters = []

            def select(self, *_args): return self
            def eq(self, key, value):
                self.filters.append((key, value))
                return self
            def order(self, *_args, **_kwargs): return self
            def limit(self, *_args): return self
            def execute(self):
                if self.table.name == "sources":
                    data = [{"id": "crossref"}]
                elif ("status", "success") in self.filters:
                    data = [{"id": "last-success"}]
                else:
                    data = []
                return type("Response", (), {"data": data})()

        class Table:
            def __init__(self, name):
                self.name = name
            def __call__(self): return Query(self)

        class Client:
            def __init__(self):
                self.tables = {name: Table(name) for name in ("sources", "fetch_runs")}
            def table(self, name): return self.tables[name]()

        # The query must exclude the retained success before selecting expired runs.
        client = Client()
        with patch.object(cleanup, "_delete_in_batches", return_value=0) as delete:
            cleanup._delete_old_fetch_runs(client, retention_days=3)
        self.assertEqual(delete.call_args.kwargs["excluded_ids"], ["last-success"])


if __name__ == "__main__":
    unittest.main()
