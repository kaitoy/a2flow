import path from 'path';
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Self-contained server bundle consumed by frontend/Dockerfile.
  output: 'standalone',
  outputFileTracingRoot: __dirname,
  // Next 16.3 writes AGENTS.md / CLAUDE.md into frontend/ on every dev and
  // build. This repo curates its own agent instructions (root CLAUDE.md and
  // .claude/rules/), so opt out of the generated ones.
  agentRules: false,
  // The /api/* and /openapi.json → backend proxy lives in src/proxy.ts, so it
  // can read BACKEND_BASE_URL at container start instead of at build time.
  turbopack: {
    resolveAlias: {
      crypto: './src/lib/crypto-shim.ts',
    },
  },
  webpack(config, { isServer }) {
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        net: false,
        tls: false,
        crypto: false,
      };
    }
    return config;
  },
};

export default nextConfig;
