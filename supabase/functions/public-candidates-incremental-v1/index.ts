import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { authorizeRequest, corsHeaders } from "../_shared/auth.ts";

const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
const harvesterSupabaseSecretKey = Deno.env.get("HARVESTER_SUPABASE_SECRET_KEY") ?? "";

serve(async (request) => {
  const authError = authorizeRequest(request);
  if (authError) return authError;

  const url = new URL(request.url);
  const updatedSince = url.searchParams.get("updated_since");
  if (!updatedSince) {
    return new Response(JSON.stringify({ error: "updated_since is required" }), {
      status: 400,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  }

  const limit = Math.min(Number(url.searchParams.get("limit") ?? "200"), 1000);
  const offset = Number(url.searchParams.get("offset") ?? "0");
  const supabase = createClient(supabaseUrl, harvesterSupabaseSecretKey);

  const { data, error, count } = await supabase
    .from("api_candidates_v1")
    .select("*", { count: "exact" })
    .gte("updated_at", updatedSince)
    .order("updated_at", { ascending: true })
    .range(offset, offset + limit - 1);

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
