import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { authorizeRequest, corsHeaders } from "../_shared/auth.ts";
import { resolveFacetRpcResult } from "./payload.ts";

const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
const harvesterSupabaseSecretKey = Deno.env.get("HARVESTER_SUPABASE_SECRET_KEY") ?? "";

serve(async (request) => {
  const authError = authorizeRequest(request);
  if (authError) return authError;

  try {
    const supabase = createClient(supabaseUrl, harvesterSupabaseSecretKey);
    const { data, error } = await supabase.rpc("api_candidate_facets_v1");
    const payload = resolveFacetRpcResult(data, error);
    return new Response(JSON.stringify(payload), {
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  } catch {
    return new Response(JSON.stringify({ error: "Facet aggregation unavailable" }), {
      status: 500,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  }
});
