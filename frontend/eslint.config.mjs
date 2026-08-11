import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,

  // Architecture guardrail (ADR 008): services/ is the only layer that knows a
  // network exists. A component that fetches cannot be tested without one, so
  // the rule is enforced by the linter rather than by convention alone.
  {
    rules: {
      "no-restricted-globals": [
        "error",
        {
          name: "fetch",
          message:
            "Only services/ may call the network. Import a function from services/ instead.",
        },
      ],
    },
  },
  {
    files: ["services/**", "**/*.test.ts", "**/*.test.tsx", "vitest.setup.ts"],
    rules: { "no-restricted-globals": "off" },
  },

  // Generated from the FastAPI OpenAPI schema; not ours to lint or edit.
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "coverage/**",
    "next-env.d.ts",
    "types/api.generated.ts",
  ]),

  // Must stay last: turns off stylistic rules that would fight Prettier.
  prettier,
]);

export default eslintConfig;
