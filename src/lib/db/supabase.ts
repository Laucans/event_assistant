import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// Framework-agnostic on purpose: no "server-only", no next/* imports and no
// "@/" path alias, because scripts/check-db.mts runs this file under plain
// Node, which resolves none of those. The client/server boundary here is
// therefore documentary — nothing leaks (Next inlines only NEXT_PUBLIC_ vars,
// so SUPABASE_SECRET_KEY is undefined in the browser bundle), but the split is
// upheld by convention, not by the compiler.
//
// Both factories are functions rather than module-level singletons: a
// top-level createClient() would read the env vars at import time, and
// `next build` imports the module without them. Each caches its instance on
// first call, because createClient() also builds a GoTrue auth client, and
// several of those against the same storage key warn and race.

let publicInstance: SupabaseClient | undefined;
let serviceInstance: SupabaseClient | undefined;

/** Publishable key — safe in the browser; RLS policies govern access. */
export function publicClient(): SupabaseClient {
  publicInstance ??= createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!
  );
  return publicInstance;
}

/** Secret key — bypasses RLS. Server and scripts only, never the browser. */
export function serviceClient(): SupabaseClient {
  serviceInstance ??= createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SECRET_KEY!
  );
  return serviceInstance;
}
