/**
 * pnpm hooks for the frontend install.
 *
 * Some dependencies declare a peer the project has moved past a major of.
 * A peer always resolves to the project's own copy, so each entry below turns
 * such a peer into a regular dependency on the version the package supports.
 * Drop an entry once its package supports the project's version.
 *
 * - @hey-api/openapi-ts imports TypeScript's classic compiler API at runtime,
 *   which TypeScript 7 no longer ships; give it the TypeScript 6 API package.
 * - @a2ui/react's types must share @a2ui/web_core's Zod 3, not the project's
 *   Zod 4.
 */
const PEERS_TO_PIN = {
  "@hey-api/openapi-ts": { typescript: "npm:@typescript/typescript6@^6.0.2" },
  "@a2ui/react": { zod: "^3.25.76" },
};

module.exports = {
  hooks: {
    readPackage(pkg) {
      const pins = PEERS_TO_PIN[pkg.name];
      if (pins) {
        for (const [name, range] of Object.entries(pins)) {
          delete pkg.peerDependencies?.[name];
          pkg.dependencies = { ...pkg.dependencies, [name]: range };
        }
      }
      return pkg;
    },
  },
};
