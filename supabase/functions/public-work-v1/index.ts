import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { authorizeRequest, corsHeaders } from "../_shared/auth.ts";

const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
const harvesterSupabaseSecretKey = Deno.env.get("HARVESTER_SUPABASE_SECRET_KEY") ?? "";

serve(async (request) => {
  const authError = authorizeRequest(request);
  if (authError) return authError;

  const url = new URL(request.url);
  const id = url.searchParams.get("id");
  const doi = url.searchParams.get("doi");

  if ((!id && !doi) || (id && doi)) {
    return new Response(JSON.stringify({ error: "provide exactly one of id or doi" }), {
      status: 400,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  }

  const supabase = createClient(supabaseUrl, harvesterSupabaseSecretKey);

  let query = supabase.from("api_candidates_v1").select("*").limit(1);
  query = id ? query.eq("id", id) : query.eq("doi", doi);

  const { data, error } = await query.maybeSingle();
  if (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  }

  return new Response(JSON.stringify({ data }), {
    headers: { "Content-Type": "application/json", ...corsHeaders },
  });
});
