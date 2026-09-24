import assert from "node:assert/strict";
import { test } from "node:test";
import { sourceRunStatus } from "../supabase/functions/public-status-v1/freshness.ts";

const now = Date.parse("2026-03-03T00:00:00Z");
const run = (source, status, started_at, window_end) => ({
  source, status, started_at, finished_at: started_at,
  window_start: "2026-03-01T00:00:00Z", window_end,
});

test("failed latest attempt retains the last successful Crossref sample", () => {
  const successful = run("crossref", "success", "2026-03-02T00:00:00Z", "2026-03-02T00:00:00Z");
  const failed = run("crossref", "failed", "2026-03-02T12:00:00Z", "2026-03-02T12:00:00Z");
  const status = sourceRunStatus([successful, failed], now)("crossref");
  assert.equal(status.latest_run, failed);
  assert.equal(status.last_successful_run, successful);
  assert.deepEqual(status.freshness, {
    state: "sampled", fresh_through: "2026-03-02T00:00:00Z", lag_seconds: 86400,
  });
});

test("no prior successful run is explicitly unknown", () => {
  const status = sourceRunStatus([
    run("arxiv", "failed", "2026-03-02T12:00:00Z", "2026-03-02T12:00:00Z"),
  ], now)("arxiv");
  assert.equal(status.latest_run.status, "failed");
  assert.equal(status.last_successful_run, null);
  assert.deepEqual(status.freshness, {
    state: "no_success", fresh_through: null, lag_seconds: null,
  });
});

test("latest successful sample follows maximum completed window, not latest attempt", () => {
  const status = sourceRunStatus([
    run("crossref", "success", "2026-03-02T12:00:00Z", "2026-03-01T12:00:00Z"),
    run("crossref", "success", "2026-03-02T00:00:00Z", "2026-03-02T00:00:00Z"),
  ], now)("crossref");
  assert.equal(status.freshness.fresh_through, "2026-03-02T00:00:00Z");
  assert.equal(status.freshness.state, "sampled");
});

test("complete-window sources still report covered freshness", () => {
  const status = sourceRunStatus([
    run("arxiv", "success", "2026-03-02T00:00:00Z", "2026-03-02T00:00:00Z"),
  ], now)("arxiv");
  assert.equal(status.freshness.state, "covered");
});
