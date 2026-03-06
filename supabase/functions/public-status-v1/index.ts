import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { authorizeRequest, corsHeaders } from "../_shared/auth.ts";

const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
const harvesterSupabaseSecretKey = Deno.env.get("HARVESTER_SUPABASE_SECRET_KEY") ?? "";

serve(async (request) => {
  const authError = authorizeRequest(request);
  if (authError) return authError;

  const supabase = createClient(supabaseUrl, harvesterSupabaseSecretKey);

  const [sourcesResult, runsResult, countsResult] = await Promise.all([
    supabase.from("sources").select("id,name,enabled,updated_at").order("id", { ascending: true }),
    supabase
      .from("fetch_runs")
      .select("source,status,finished_at,window_start,window_end")
      .order("finished_at", { ascending: false }),
    supabase.from("works").select("id", { count: "exact", head: true }),
  ]);

  if (sourcesResult.error) {
    return new Response(JSON.stringify({ error: sourcesResult.error.message }), {
      status: 500,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  }
  if (runsResult.error) {
    return new Response(JSON.stringify({ error: runsResult.error.message }), {
      status: 500,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  }
  if (countsResult.error) {
    return new Response(JSON.stringify({ error: countsResult.error.message }), {
      status: 500,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  }

  const latestRunBySource = new Map<string, Record<string, unknown>>();
  for (const run of runsResult.data ?? []) {
    if (!latestRunBySource.has(run.source)) {
      latestRunBySource.set(run.source, run);
    }
  }

  const sources = (sourcesResult.data ?? []).map((source) => {
    const latestRun = latestRunBySource.get(source.id);
    return {
      id: source.id,
      name: source.name,
      enabled: source.enabled,
      updated_at: source.updated_at,
      latest_run: latestRun ?? null,
    };
  });

  return new Response(
    JSON.stringify({
      sources,
      works_total: countsResult.count ?? 0,
    }),
    { headers: { "Content-Type": "application/json", ...corsHeaders } },
  );
});
