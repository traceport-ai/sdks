import { defineConfig } from "tsup";

// Dual ESM + CommonJS bundles with matching declarations. Dependencies and peer dependencies
// (other @traceport packages) are left as imports, never bundled, so every product shares one
// copy of @traceport/core at runtime.
export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm", "cjs"],
  dts: true,
  tsconfig: "tsconfig.build.json",
  sourcemap: true,
  clean: true,
  target: "es2022",
  platform: "neutral",
  splitting: false,
  treeshake: true,
});
