import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { authorizeRequest, corsHeaders } from "../_shared/auth.ts";

const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
const harvesterSupabaseSecretKey = Deno.env.get("HARVESTER_SUPABASE_SECRET_KEY") ?? "";

serve(async (request) => {
  const authError = authorizeRequest(request);
  if (authError) return authError;

  const url = new URL(request.url);
  const limit = Math.min(Number(url.searchParams.get("limit") ?? "200"), 1000);
  const offset = Number(url.searchParams.get("offset") ?? "0");
  const since = url.searchParams.get("since");
  const until = url.searchParams.get("until");
  const updatedSince = url.searchParams.get("updated_since");
  const includePreprints = url.searchParams.get("include_preprints");
  const candidateTypes = (url.searchParams.get("candidate_types") ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const candidateGroups = (url.searchParams.get("candidate_groups") ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const sources = (url.searchParams.get("sources") ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);

  const supabase = createClient(supabaseUrl, harvesterSupabaseSecretKey);

  let query = supabase
    .from("api_candidates_v1")
    .select("*", { count: "exact" })
    .order("updated_at", { ascending: false })
    .range(offset, offset + limit - 1);

  if (since) query = query.gte("published_at", since);
  if (until) query = query.lte("published_at", until);
  if (updatedSince) query = query.gte("updated_at", updatedSince);
  if (includePreprints === "false") query = query.eq("is_preprint", false);
  if (sources.length > 0) query = query.in("source", sources);
  if (candidateTypes.length > 0) query = query.in("candidate_type", candidateTypes);
  if (candidateGroups.length > 0) query = query.in("candidate_group", candidateGroups);

  const { data, error, count } = await query;
  if (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  }

  return new Response(
    JSON.stringify({
      data: data ?? [],
      paging: {
        limit,
        offset,
        next_offset: offset + limit < (count ?? 0) ? offset + limit : null,
        total: count ?? null,
      },
    }),
    { headers: { "Content-Type": "application/json", ...corsHeaders } },
  );
});
