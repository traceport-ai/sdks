import { defineConfig } from "tsup";

// Dual ESM + CommonJS bundles with matching declarations. Dependencies and peer dependencies
// (other @traceport packages) are left as imports, never bundled, so every product shares one
// copy of @traceport/core at runtime.
//
// Core has two entry points (index and internal). Code splitting puts the modules they share
// (client registry, transport, error classes) in one chunk; without it each entry would carry its
// own copy, so products could not find clients and errors would fail `instanceof` checks.
export default defineConfig({
  entry: ["src/index.ts", "src/internal.ts"],
  format: ["esm", "cjs"],
  dts: true,
  tsconfig: "tsconfig.build.json",
  sourcemap: true,
  clean: true,
  target: "es2022",
  platform: "neutral",
  splitting: true,
  treeshake: true,
});
