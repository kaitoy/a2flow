import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "../backend/openapi.yaml",
  output: "src/generated/api",
  plugins: [
    { name: "@hey-api/typescript", enums: "javascript" },
    { name: "zod", requests: true, responses: true, definitions: true },
  ],
});
