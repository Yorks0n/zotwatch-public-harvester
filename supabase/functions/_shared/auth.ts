export const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const harvesterSupabasePublishableKey =
  Deno.env.get("HARVESTER_SUPABASE_PUBLISHABLE_KEY") ?? "";

export function authorizeRequest(request: Request): Response | null {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  const apikey = request.headers.get("apikey") ?? "";
  const authorization = request.headers.get("Authorization") ?? "";
  const bearer = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";

  if (
    harvesterSupabasePublishableKey &&
    (apikey === harvesterSupabasePublishableKey || bearer === harvesterSupabasePublishableKey)
  ) {
    return null;
  }

  return new Response(JSON.stringify({ code: 401, message: "Invalid publishable key" }), {
    status: 401,
    headers: {
      "Content-Type": "application/json",
      ...corsHeaders,
    },
  });
}
