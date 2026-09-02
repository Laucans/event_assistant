import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Explicit rather than default so build output (.next/) is never
    // scanned; covers colocated tests under src/ as well as tests/.
    include: ["{src,tests}/**/*.{test,spec}.?(c|m)[jt]s?(x)"],
  },
});
