import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { authorizeRequest, corsHeaders } from "../_shared/auth.ts";
import { sourceRunStatus } from "./freshness.ts";

const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
const harvesterSupabaseSecretKey = Deno.env.get("HARVESTER_SUPABASE_SECRET_KEY") ?? "";

serve(async (request) => {
  const authError = authorizeRequest(request);
  if (authError) return authError;

  const supabase = createClient(supabaseUrl, harvesterSupabaseSecretKey);

  const [sourcesResult, countsResult] = await Promise.all([
    supabase.from("sources").select("id,name,enabled,updated_at").order("id", { ascending: true }),
    supabase.from("works").select("id", { count: "exact", head: true }),
  ]);

  if (sourcesResult.error) {
    return new Response(JSON.stringify({ error: sourcesResult.error.message }), {
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

  const runs = [];
  const pageSize = 1000;
  for (let offset = 0;; offset += pageSize) {
    const page = await supabase
      .from("fetch_runs")
      .select("source,status,started_at,finished_at,window_start,window_end")
      .order("started_at", { ascending: false })
      .range(offset, offset + pageSize - 1);
    if (page.error) {
      return new Response(JSON.stringify({ error: page.error.message }), {
        status: 500,
        headers: { "Content-Type": "application/json", ...corsHeaders },
      });
    }
    const batch = page.data ?? [];
    runs.push(...batch);
    if (batch.length < pageSize) break;
  }
  const statusForSource = sourceRunStatus(runs, Date.now());

  const sources = (sourcesResult.data ?? []).map((source) => {
    return {
      id: source.id,
      name: source.name,
      enabled: source.enabled,
      updated_at: source.updated_at,
      ...statusForSource(source.id),
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
