import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const source = (path: string): string => fileURLToPath(new URL(path, import.meta.url));

export default defineConfig({
  resolve: {
    // Tests run against package sources, the same way tsconfig.json paths resolve them.
    // More specific entries first: "@traceport/core/internal" must not match "@traceport/core".
    alias: [
      {
        find: /^@traceport\/core\/internal$/,
        replacement: source("./packages/core/src/internal.ts"),
      },
      { find: /^@traceport\/core$/, replacement: source("./packages/core/src/index.ts") },
      { find: /^@traceport\/workflows$/, replacement: source("./packages/workflows/src/index.ts") },
    ],
  },
  test: {
    include: ["packages/*/test/**/*.test.ts"],
    environment: "node",
    // Type assertions in test files (expectTypeOf) are checked by `npm run typecheck`.
    restoreMocks: true,
  },
});
