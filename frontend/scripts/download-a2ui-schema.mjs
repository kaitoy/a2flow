import { createHash } from 'node:crypto';
import { existsSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const url = 'https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json';
const outputPath = join(__dirname, '../src/generated/basic_catalog.json');
// Pins the exact published bytes so a compromised/altered upstream response
// fails the build instead of being silently baked into the app. Recompute
// with `curl -s <url> | sha256sum` and update deliberately when a2ui.org
// intentionally revises the catalog.
const EXPECTED_SHA256 = '8cc94d0a482e67048f9fc989964ca5da56fe42f531d919315a508989fb22e13e';

if (existsSync(outputPath)) {
  console.log(`${outputPath} already exists, skipping download.`);
  process.exit(0);
}

console.log(`Downloading ${url}...`);
const response = await fetch(url);
if (!response.ok) {
  throw new Error(`Failed to download basic_catalog.json: ${response.status} ${response.statusText}`);
}
const raw = Buffer.from(await response.arrayBuffer());
const actualSha256 = createHash('sha256').update(raw).digest('hex');
if (actualSha256 !== EXPECTED_SHA256) {
  throw new Error(
    `basic_catalog.json integrity check failed: expected sha256 ${EXPECTED_SHA256}, got ${actualSha256}.`
  );
}
const data = JSON.parse(raw.toString('utf8'));
mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, JSON.stringify(data, null, 2));
console.log(`Saved to src/generated/basic_catalog.json`);
