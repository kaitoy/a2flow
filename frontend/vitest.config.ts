import path from "path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
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
    },
  },
  define: {
    "process.env.BACKEND_BASE_URL": JSON.stringify("http://localhost:8000"),
    "process.env.NODE_ENV": JSON.stringify("test"),
  },
});
