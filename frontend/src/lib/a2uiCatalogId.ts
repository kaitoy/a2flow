/**
 * Canonical id of the A2UI basic catalog used across the app.
 *
 * Kept in a dependency-free module so the Redux store and API layer can
 * reference it without importing the `@a2ui/*` renderer stack. Must match the
 * id the `tailwindCatalog` is registered under (`src/components/a2uiCatalog.tsx`)
 * and the URL `scripts/download-a2ui-schema.mjs` downloads: the A2UI message
 * processor resolves each `createSurface.catalogId` strictly against the
 * registered catalog ids, so every path that fabricates or defaults a
 * `catalogId` has to agree on this value.
 */
export const A2UI_CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json";
