import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const here = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": here },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: [resolve(here, "tests/setup.ts")],
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});
