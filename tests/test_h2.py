from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

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
                if fetcher.source_name in {"biorxiv", "medrxiv"}:
                    raise UpstreamUnavailableError(f"{fetcher.source_name} unavailable")
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

    def test_enabled_preprint_source_failure_is_partial_failure(self):
        result, attempted = self.invoke(["crossref", "biorxiv", "medrxiv"], failures={"biorxiv"})
        self.assertEqual(result.status, "partial_failed")
        self.assertEqual(result.failed, ("biorxiv",))
        self.assertNotIn("biorxiv", result.skipped)
        self.assertEqual(result.succeeded, ("crossref", "medrxiv"))
        self.assertEqual(attempted, ["crossref", "biorxiv", "medrxiv"])

    def test_both_enabled_preprint_sources_fail_without_hiding_failure(self):
        result, attempted = self.invoke(
            ["crossref", "arxiv", "biorxiv", "medrxiv"],
            failures={"biorxiv", "medrxiv"},
        )
        self.assertEqual(result.status, "partial_failed")
        self.assertEqual(result.succeeded, ("crossref", "arxiv"))
        self.assertEqual(result.failed, ("biorxiv", "medrxiv"))
        self.assertEqual(result.skipped, ("openalex",))
        self.assertEqual(attempted, ["crossref", "arxiv", "biorxiv", "medrxiv"])

    def test_disabled_preprint_source_is_skipped_without_attempt(self):
        result, attempted = self.invoke(["crossref", "medrxiv"])
        self.assertEqual(result.status, "success")
        self.assertEqual(result.failed, ())
        self.assertIn("biorxiv", result.skipped)
        self.assertEqual(attempted, ["crossref", "medrxiv"])

    def test_failed_preprint_run_keeps_cursor_and_error_summary_opaque(self):
        db = MultiSourceDatabase()
        db.cursors[("biorxiv", "updated_from")] = "2026-09-23"
        attempted = []
        responses = []
        real_client = httpx.Client

        def upstream(_request: httpx.Request) -> httpx.Response:
            responses.append(1)
            return httpx.Response(200, headers={"content-type": "application/json"},
                                  text="<html>secret upstream content</html>")

        def successful_source(*, fetcher, **_kwargs):
            attempted.append(fetcher.source_name)

        with patch.object(harvest_all, "get_supabase_client", return_value=db), patch.object(
            harvest_all, "fetch_enabled_sources",
            return_value=[{"id": name} for name in ("crossref", "biorxiv", "medrxiv")]
        ), patch.object(harvest_all, "_run_crossref_harvest", side_effect=successful_source), patch.object(
            harvest_all, "_run_biorxiv_family_harvest", wraps=harvest_all._run_biorxiv_family_harvest
        ), patch.object(harvest_all.MedRxivFetcher, "fetch", side_effect=lambda _window: attempted.append("medrxiv") or []
        ), patch("src.fetchers.biorxiv.httpx.Client",
                 side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(upstream), **kwargs)
        ), patch("src.fetchers.http.time.sleep"), patch.object(
            harvest_all, "run_cleanup"
        ), patch("builtins.print") as output:
            result = harvest_all.run_harvest_all()

        self.assertEqual(result.status, "partial_failed")
        self.assertEqual(result.failed, ("biorxiv",))
        self.assertNotIn("biorxiv", result.skipped)
        self.assertEqual(attempted, ["crossref", "medrxiv"])
        self.assertEqual(len(responses), 4)
        failed = next(run for run in db.runs if run["source"] == "biorxiv")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error_summary"], "UpstreamUnavailableError")
        self.assertEqual(db.cursors[("biorxiv", "updated_from")], "2026-09-23")
        self.assertNotIn("secret upstream content", str(failed["error_summary"]))
        self.assertNotIn("<html>", str(failed["error_summary"]))
        self.assertNotIn("body_prefix", str(failed["error_summary"]))
        log = "\n".join(str(call) for call in output.call_args_list)
        self.assertNotIn("secret upstream content", log)
        self.assertNotIn("<html>", log)
        self.assertNotIn("body_prefix", log)

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
