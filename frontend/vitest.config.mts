import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// .mts so Vite's native config loader reads this as ESM. In ESM there is no
// __dirname, hence import.meta.dirname (Node >= 20.11).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules/**", ".next/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      // Layers that hold logic. app/ is composition and is covered by the
      // component tests it renders, not by a coverage floor of its own.
      include: ["lib/**", "services/**", "hooks/**", "components/**"],
    },
  },
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./") },
  },
});
