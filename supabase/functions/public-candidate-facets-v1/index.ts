import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { authorizeRequest, corsHeaders } from "../_shared/auth.ts";

const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
const harvesterSupabaseSecretKey = Deno.env.get("HARVESTER_SUPABASE_SECRET_KEY") ?? "";

serve(async (request) => {
  const authError = authorizeRequest(request);
  if (authError) return authError;

  const supabase = createClient(supabaseUrl, harvesterSupabaseSecretKey);

  const { data, error } = await supabase
    .from("api_candidates_v1")
    .select("source,candidate_type,candidate_group,is_preprint");

  if (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  }

  const rows = data ?? [];
  const bySource = new Map<string, number>();
  const byType = new Map<string, number>();
  const byGroup = new Map<string, number>();
  let preprintCount = 0;
  let publishedCount = 0;

  for (const row of rows) {
    const source = String(row.source ?? "");
    const candidateType = String(row.candidate_type ?? "");
    const candidateGroup = String(row.candidate_group ?? "");

    bySource.set(source, (bySource.get(source) ?? 0) + 1);
    byType.set(candidateType, (byType.get(candidateType) ?? 0) + 1);
    byGroup.set(candidateGroup, (byGroup.get(candidateGroup) ?? 0) + 1);

    if (row.is_preprint) {
      preprintCount += 1;
    } else {
      publishedCount += 1;
    }
  }

  return new Response(
    JSON.stringify({
      totals: {
        all: rows.length,
        preprint: preprintCount,
        published: publishedCount,
      },
      sources: Object.fromEntries(bySource.entries()),
      candidate_types: Object.fromEntries(byType.entries()),
      candidate_groups: Object.fromEntries(byGroup.entries()),
    }),
    { headers: { "Content-Type": "application/json", ...corsHeaders } },
  );
});
