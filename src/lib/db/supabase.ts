import { createClient } from "@supabase/supabase-js";

// Framework-agnostic on purpose: no "server-only", no next/* imports and no
// "@/" path alias, because scripts/check-db.mts runs this file under plain
// Node, which resolves none of those.
//
// Both factories are functions rather than module-level singletons. A
// top-level createClient() would read the env vars at import time, and
// `next build` imports the module without them.

/** Publishable key — safe in the browser; RLS policies govern access. */
export function publicClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!
  );
}

/** Secret key — bypasses RLS. Server and scripts only, never the browser. */
export function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SECRET_KEY!
  );
}
