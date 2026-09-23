import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { PGlite } from "@electric-sql/pglite";

const migration = await readFile(
  new URL("../supabase/migrations/20260923000000_candidate_facets_rpc.sql", import.meta.url),
  "utf8",
);

async function database() {
  const db = new PGlite();
  await db.exec(`
    create role anon;
    create role authenticated;
    create role service_role;
    create table public.candidate_fixture (
      source text, candidate_type text, candidate_group text, is_preprint boolean
    );
    create view public.api_candidates_v1 as
      select source, candidate_type, candidate_group, is_preprint
      from public.candidate_fixture;
    grant usage on schema public to anon, authenticated, service_role;
    grant select on public.api_candidates_v1 to service_role;
  `);
  await db.exec(migration);
  return db;
}

async function facets(db) {
  const { rows } = await db.query("select public.api_candidate_facets_v1() as result");
  return rows[0].result;
}

test("SQL RPC returns the exact empty payload shape", async () => {
  const db = await database();
  try {
    assert.deepEqual(await facets(db), {
      totals: { all: 0, preprint: 0, published: 0 },
      sources: {}, candidate_types: {}, candidate_groups: {},
    });
  } finally {
    await db.close();
  }
});

test("SQL RPC includes all 1510 candidates and groups after row 1000", async () => {
  const db = await database();
  try {
    await db.exec(`
      insert into public.candidate_fixture
      select 'crossref', 'journal-article', 'article', false from generate_series(1,1005);
      insert into public.candidate_fixture
      select 'arxiv', 'preprint', 'preprint', true from generate_series(1,500);
      insert into public.candidate_fixture
      select 'medrxiv', 'preprint', 'preprint', true from generate_series(1,3);
      insert into public.candidate_fixture
      select 'biorxiv', 'dataset', 'dataset', false from generate_series(1,2);
    `);
    const result = await facets(db);
    assert.deepEqual(result, {
      totals: { all: 1510, preprint: 503, published: 1007 },
      sources: { crossref: 1005, arxiv: 500, medrxiv: 3, biorxiv: 2 },
      candidate_types: { "journal-article": 1005, preprint: 503, dataset: 2 },
      candidate_groups: { article: 1005, preprint: 503, dataset: 2 },
    });
    const authoritative = await db.query("select count(*)::int as n from public.api_candidates_v1");
    assert.equal(result.totals.all, authoritative.rows[0].n);
    for (const group of [result.sources, result.candidate_types, result.candidate_groups]) {
      assert.equal(Object.values(group).reduce((a, b) => a + b, 0), result.totals.all);
    }
  } finally {
    await db.close();
  }
});

test("RPC privilege boundary and invoker context are enforced", async () => {
  const db = await database();
  try {
    const { rows } = await db.query(`
      select
        has_function_privilege('anon', 'public.api_candidate_facets_v1()', 'EXECUTE') as anon,
        has_function_privilege('authenticated', 'public.api_candidate_facets_v1()', 'EXECUTE') as authenticated,
        has_function_privilege('service_role', 'public.api_candidate_facets_v1()', 'EXECUTE') as service_role,
        exists (
          select 1 from aclexplode(p.proacl) acl
          where acl.grantee = 0 and acl.privilege_type = 'EXECUTE'
        ) as public_execute,
        p.prosecdef as security_definer,
        p.proconfig as function_config,
        pg_get_functiondef(p.oid) as definition
      from pg_proc p
      where p.oid = 'public.api_candidate_facets_v1()'::regprocedure
    `);
    const row = rows[0];
    assert.equal(row.anon, false);
    assert.equal(row.authenticated, false);
    assert.equal(row.service_role, true);
    assert.equal(row.public_execute, false);
    assert.equal(row.security_definer, false);
    assert.ok(row.function_config.includes("search_path=pg_catalog, public"));
    assert.match(row.definition, /from public\.api_candidates_v1/i);
    assert.doesNotMatch(row.definition, /\bexecute\b|\bformat\s*\(/i);

    await db.exec("set role anon");
    await assert.rejects(db.query("select public.api_candidate_facets_v1()"), /permission denied/i);
    await db.exec("reset role");
    await db.exec("set role authenticated");
    await assert.rejects(db.query("select public.api_candidate_facets_v1()"), /permission denied/i);
    await db.exec("reset role");
    await db.exec("set role service_role");
    assert.deepEqual(await facets(db), {
      totals: { all: 0, preprint: 0, published: 0 },
      sources: {}, candidate_types: {}, candidate_groups: {},
    });
    await db.exec("reset role");
  } finally {
    await db.close();
  }
});
