import { describe, expect, it } from "vitest";
import { publicClient, serviceClient } from "./supabase";

// createClient() never makes a network call at construction time, so these
// stand-in values are enough to exercise the caching behaviour without a
// real Supabase project.
process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_test";
process.env.SUPABASE_SECRET_KEY = "sb_secret_test";

describe("supabase client factories", () => {
  it("publicClient caches its instance across calls", () => {
    expect(publicClient()).toBe(publicClient());
  });

  it("serviceClient caches its instance across calls", () => {
    expect(serviceClient()).toBe(serviceClient());
  });

  it("publicClient and serviceClient are distinct instances", () => {
    expect(publicClient()).not.toBe(serviceClient());
  });
});
