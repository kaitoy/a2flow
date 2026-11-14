/**
 * Writes the A2UI Basic Catalog document the agent is told about
 * (`src/generated/basic_catalog.json`, read by `createA2UIMiddleware`).
 *
 * The document comes from the installed renderer, not from a2ui.org: the
 * renderer validates every component the agent sends against its own strict
 * schemas, so the catalog the agent sees has to be exactly those schemas.
 * The published document can run ahead of the renderer release -- it gained
 * `List.listStyle`, which `@a2ui/web_core` 0.14/0.15 rejects -- and an agent
 * following it would produce surfaces that fail to render. `basicCatalog.toJson()`
 * reproduces the published document for the version the renderer implements,
 * and is regenerated on every run so a dependency bump carries the catalog
 * along with it.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { basicCatalog } from '@a2ui/web_core/v0_9/basic_catalog';

const outputPath = join(dirname(fileURLToPath(import.meta.url)), '../src/generated/basic_catalog.json');

mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, JSON.stringify(basicCatalog.toJson(), null, 2));
console.log('Generated src/generated/basic_catalog.json');
