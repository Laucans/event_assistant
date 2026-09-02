import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // An unrelated package-lock.json sits in a parent directory, so Next infers
  // the wrong workspace root. Pin it to this repo.
  turbopack: {
    root: path.resolve(import.meta.dirname),
  },
  // `next dev` otherwise appends a managed block to CLAUDE.md on every boot.
  // CLAUDE.md is hand-authored here (edits go through the vibe-specialist
  // subagent), so keep the generator out of it.
  agentRules: false,
};

export default nextConfig;
