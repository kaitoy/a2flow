import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "../backend/openapi.yaml",
  output: "src/generated/api",
  plugins: [
    "@hey-api/client-fetch",
    { name: "@hey-api/typescript", enums: "javascript" },
    { name: "@hey-api/sdk", validator: { response: "zod" } },
    { name: "zod", requests: true, responses: true, definitions: true },
  ],
});
