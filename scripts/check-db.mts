// Proves this machine can reach the Supabase project over the network with
// both keys. Run it with `npm run db:check`.
//
// .mts on purpose: package.json has no "type": "module", so a plain .ts entry
// point is treated as CommonJS and `import` throws. The relative import below
// carries its .ts extension because Node requires it — which is why
// tsconfig.json sets allowImportingTsExtensions.
//
// Nothing here ever prints a key: only its label and the HTTP status.
import { serviceClient } from "../src/lib/db/supabase.ts";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
const secretKey = process.env.SUPABASE_SECRET_KEY;

function fail(message: string): never {
  console.error(`FAIL  ${message}`);
  process.exit(1);
}

// Checked one at a time rather than in a loop so that `fail`'s `never` return
// narrows each const to `string` for the probes below.
const missing = "is not set — copy .env.example and fill it in";
if (!url) fail(`NEXT_PUBLIC_SUPABASE_URL ${missing}`);
if (!publishableKey) fail(`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ${missing}`);
if (!secretKey) fail(`SUPABASE_SECRET_KEY ${missing}`);

// Both key types authenticate against the probes below, so reachability alone
// cannot tell them apart: a secret key pasted into the NEXT_PUBLIC_ variable
// would pass every check here and then be inlined into the browser bundle by
// `next build`, publishing an RLS-bypassing credential. Assert the type.
// Legacy anon / service_role JWTs (they start "eyJ") are rejected the same
// way — Supabase retires them at the end of 2026.
function requireKeyType(name: string, value: string, prefix: string): void {
  if (value.startsWith(prefix)) return;
  fail(
    value.startsWith("eyJ")
      ? `${name} holds a legacy JWT — this project uses the opaque ${prefix}… keys from Settings -> API Keys`
      : `${name} does not look like a ${prefix}… key`
  );
}

requireKeyType(
  "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
  publishableKey,
  "sb_publishable_"
);
requireKeyType("SUPABASE_SECRET_KEY", secretKey, "sb_secret_");

// Trailing slashes are easy to paste in and would produce "//rest/v1/", whose
// 404 looks like a dead project rather than a malformed URL.
const baseUrl = url.replace(/\/+$/, "");

// Probe A — authentication and reachability.
//
// The two key types do not answer to the same endpoint. The secret key can
// read PostgREST's OpenAPI root (/rest/v1/), which describes the schema and
// needs no tables. The publishable key cannot: Supabase rejects it there with
// 401 "Only secret API keys can be used for this endpoint." So the publishable
// key is probed against a table path instead, where a *missing* table (404
// PGRST205) still proves the key authenticated — an invalid key never gets
// that far, it is turned away with 401 "Invalid API key".
//
// The probe table is deliberately a name no migration will ever create. A real
// table would make this check mean two different things either side of its
// migration (404 before, 200 after), and a 200 with zero rows — what RLS
// returns to the publishable key on a table with no read policy — would pass
// for the same reason as a 404. Against a name that never exists, the
// missing-table 404 is the answer forever, so the probe keeps one meaning.
// Schema state is Probe B's job, below.
//
// Either way a connect failure means the URL is wrong or the project is
// paused, and nothing here ever prints a key.
const MISSING_TABLE_CODES = new Set(["42P01", "PGRST205"]);
const PROBE_TABLE = "__connectivity_probe__";

async function get(
  path: string,
  key: string,
  label: string
): Promise<Response> {
  try {
    return await fetch(`${baseUrl}${path}`, {
      headers: { apikey: key, Authorization: `Bearer ${key}` },
    });
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    fail(`${label}: could not reach ${baseUrl} — ${reason}`);
  }
}

/** The PostgREST error code in a response body, when it is a known one. */
async function missingTableCode(response: Response): Promise<string | null> {
  const body: unknown = await response.json().catch(() => null);
  if (body && typeof body === "object" && "code" in body) {
    const code = (body as { code?: unknown }).code;
    if (typeof code === "string" && MISSING_TABLE_CODES.has(code)) return code;
  }
  return null;
}

async function probeSecretKey(key: string): Promise<void> {
  const label = "secret key";
  const response = await get("/rest/v1/", key, label);
  if (response.status !== 200) {
    fail(
      `${label}: expected HTTP 200 from /rest/v1/, got ${response.status} ${response.statusText}`
    );
  }
  console.log(`OK    ${label}: authenticated against /rest/v1/ (HTTP 200)`);
}

async function probePublishableKey(key: string): Promise<void> {
  const label = "publishable key";
  const path = `/rest/v1/${PROBE_TABLE}?select=*&limit=1`;
  const response = await get(path, key, label);

  // The missing-table 404 *is* the pass, and only when PostgREST names the
  // table as the reason: a bare 404 means something else entirely and must not
  // be read as proof that the key authenticated.
  if (response.status !== 404) {
    fail(
      `${label}: expected a missing-table 404 from ${path}, got ${response.status} ${response.statusText}`
    );
  }
  const code = await missingTableCode(response);
  if (!code) {
    fail(`${label}: unexpected 404 from ${path} — not a missing-table error`);
  }
  console.log(
    `OK    ${label}: authenticated against ${path} (HTTP 404, ${code} — the probe table never exists by design)`
  );
}

await probePublishableKey(publishableKey);
await probeSecretKey(secretKey);

// Probe B — schema state. Informational until task 4 creates `cities`: a
// missing table is the expected answer today, anything else is a real error.
// PostgREST reports a missing table as 42P01 or PGRST205 depending on its
// version, so match either rather than one hard-coded code (MISSING_TABLE_CODES
// above).
const { data, error } = await serviceClient()
  .from("cities")
  .select("*")
  .limit(1);

if (error) {
  if (MISSING_TABLE_CODES.has(error.code)) {
    console.log(
      `OK    cities not migrated yet (expected before task 4) — code ${error.code}: ${error.message}`
    );
  } else {
    fail(`cities query failed — code ${error.code}: ${error.message}`);
  }
} else {
  console.log(`OK    cities readable — ${data.length} row(s) returned`);
}

console.log("PASS  Supabase project reachable with both keys.");
