import path from "path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    // happy-dom rather than jsdom. The suite's cost is dominated by per-file
    // fixed overhead -- ~140 files each build a DOM from scratch -- and
    // happy-dom builds one far more cheaply. What it lacks is a layout engine,
    // but jsdom has none either, so the tests that need real measurements were
    // already stubbing them. See src/test/setup.ts for the API differences.
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    // Worker threads rather than child processes: threads pay the same
    // per-file setup far more cheaply than forks on this Windows host.
    pool: "threads",
    // Sized for a standalone `pnpm test`: 75% of logical cores beat both 50%
    // and 100%, since going past the physical core count oversubscribes
    // rather than parallelizes.
    //
    // A `pre-commit` run is a different story -- it also spins up
    // backend-pytest's `-n auto`, capped at 50% of cores by a
    // pytest_xdist_auto_num_workers hook in backend/tests/conftest.py -- so
    // lefthook.yml passes `--maxWorkers=50%` there to keep the two suites
    // from oversubscribing the CPU and flaking on timeouts.
    maxWorkers: "75%",
    // Vitest's 5000ms default is exactly Testing Library's `asyncUtilTimeout`
    // (src/test/setup.ts), which would let a killed test mask the assertion
    // that was actually waiting. Keep it comfortably above that.
    testTimeout: 15_000,
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/test/**", "src/generated/**", "src/**/*.d.ts"],
    },
    server: {
      deps: {
        inline: [
          "@ag-ui/client",
          "@ag-ui/core",
          "@ag-ui/a2ui-middleware",
          "@a2ui/react",
          "@a2ui/web_core",
        ],
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "next/navigation": path.resolve(__dirname, "./src/test/mocks/next-navigation.ts"),
      "next/font/google": path.resolve(__dirname, "./src/test/mocks/next-font.ts"),
      "next/image": path.resolve(__dirname, "./src/test/mocks/next-image.tsx"),
    },
  },
  define: {
    "process.env.BACKEND_BASE_URL": JSON.stringify("http://localhost:8000"),
    // The app talks to the same-origin proxy by default (empty base); tests use
    // an absolute base so the MSW handlers (registered against localhost:8000)
    // intercept the requests.
    "process.env.NEXT_PUBLIC_API_BASE": JSON.stringify("http://localhost:8000"),
    "process.env.NODE_ENV": JSON.stringify("test"),
  },
});
