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
// Either way a connect failure means the URL is wrong or the project is
// paused, and nothing here ever prints a key.
const MISSING_TABLE_CODES = new Set(["42P01", "PGRST205"]);
const PROBE_TABLE = "cities";

async function get(
  path: string,
  key: string,
  label: string
): Promise<Response> {
  try {
    return await fetch(`${url}${path}`, {
      headers: { apikey: key, Authorization: `Bearer ${key}` },
    });
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    fail(`${label}: could not reach ${url} — ${reason}`);
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

  // 404 is only accepted when PostgREST says the table is missing; a bare 404
  // would mean something else entirely and must not pass for authentication.
  if (response.status === 404) {
    const code = await missingTableCode(response);
    if (!code) {
      fail(`${label}: unexpected 404 from ${path} — not a missing-table error`);
    }
    console.log(
      `OK    ${label}: authenticated against ${path} (HTTP 404, ${code} — table not migrated yet)`
    );
    return;
  }
  if (response.status !== 200) {
    fail(
      `${label}: expected HTTP 200 or a missing-table 404 from ${path}, got ${response.status} ${response.statusText}`
    );
  }
  console.log(`OK    ${label}: authenticated against ${path} (HTTP 200)`);
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
