import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Last: turns off every formatting rule so Prettier owns formatting.
  prettier,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // The pipeline venv vendors JS (CrewAI ships a flow visualizer). It is
    // gitignored, so CI never sees it, but a local `npm run lint` would
    // report a dependency's code as if it were ours.
    "pipeline/.venv/**",
  ]),
]);

export default eslintConfig;
