/**
 * pnpm hooks for the frontend install.
 *
 * TypeScript 7 ships no classic compiler API, which @hey-api/openapi-ts
 * imports at runtime. Its `typescript` peer dependency would resolve to the
 * project's TypeScript 7, so swap the peer for a regular dependency on the
 * TypeScript 6 API package. Drop this once openapi-ts supports TypeScript 7.
 */
module.exports = {
  hooks: {
    readPackage(pkg) {
      if (pkg.name === "@hey-api/openapi-ts") {
        delete pkg.peerDependencies?.typescript;
        pkg.dependencies = {
          ...pkg.dependencies,
          typescript: "npm:@typescript/typescript6@^6.0.2",
        };
      }
      return pkg;
    },
  },
};
