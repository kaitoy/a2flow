import { writeFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const url = 'https://a2ui.org/specification/v0_9/basic_catalog.json';
const outputPath = join(__dirname, '../src/generated/basic_catalog.json');

console.log(`Downloading ${url}...`);
const response = await fetch(url);
if (!response.ok) {
  throw new Error(`Failed to download basic_catalog.json: ${response.status} ${response.statusText}`);
}
const data = await response.json();
mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, JSON.stringify(data, null, 2));
console.log(`Saved to src/generated/basic_catalog.json`);
