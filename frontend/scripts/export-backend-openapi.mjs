import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const backendDir = resolve(__dirname, "../../backend");

console.log(`Exporting OpenAPI spec from ${backendDir}...`);

const result = spawnSync("uv", ["run", "python", "-m", "scripts.export_openapi"], {
  cwd: backendDir,
  stdio: "inherit",
  shell: true,
});

if (result.error) {
  console.error("Failed to invoke 'uv'. Is it installed and on PATH?");
  console.error(result.error.message);
  process.exit(1);
}

if (result.status !== 0) {
  process.exit(result.status ?? 1);
}
