import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { resolveFacetRpcResult } from "../supabase/functions/public-candidate-facets-v1/payload.ts";

const expected = {
  totals: { all: 3, preprint: 1, published: 2 },
  sources: { crossref: 2, arxiv: 1 },
  candidate_types: { article: 2, preprint: 1 },
  candidate_groups: { article: 2, preprint: 1 },
};

test("valid RPC output retains the existing successful response schema", () => {
  const output = resolveFacetRpcResult(expected, null);
  assert.deepEqual(output, expected);
  assert.deepEqual(Object.keys(JSON.parse(JSON.stringify(output))).sort(), [
    "candidate_groups", "candidate_types", "sources", "totals",
  ]);
  assert.deepEqual(Object.keys(output.totals).sort(), ["all", "preprint", "published"]);
});

test("RPC error and unavailable result fail closed", () => {
  assert.throws(() => resolveFacetRpcResult(expected, { message: "database failed" }), /unavailable/);
  assert.throws(() => resolveFacetRpcResult(null, null), /unavailable/);
});

test("malformed RPC result and inconsistent group sums fail closed", () => {
  for (const bad of [
    { ...expected, rows: [{ title: "must not appear" }] },
    { ...expected, totals: { ...expected.totals, extra: 0 } },
    { ...expected, totals: { ...expected.totals, all: "3" } },
    { ...expected, totals: { ...expected.totals, all: 4 } },
    { ...expected, sources: { crossref: 2 } },
    { ...expected, candidate_types: [] },
    { ...expected, candidate_groups: { article: -1, preprint: 4 } },
  ]) {
    assert.throws(() => resolveFacetRpcResult(bad, null), /unavailable/);
  }
});

test("Edge entrypoint calls only the RPC and has no row-fetch fallback", async () => {
  const index = await readFile(
    new URL("../supabase/functions/public-candidate-facets-v1/index.ts", import.meta.url),
    "utf8",
  );
  assert.match(index, /\.rpc\("api_candidate_facets_v1"\)/);
  assert.match(index, /resolveFacetRpcResult\(data, error\)/);
  assert.match(index, /status: 500/);
  assert.doesNotMatch(index, /\.from\(|\.select\(|\.range\(|\.limit\(/);
});
