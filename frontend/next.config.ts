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
  // TypeScript 7 has no compiler API for `next build` to type-check through,
  // so run its `tsc` CLI instead.
  experimental: {
    useTypeScriptCli: true,
  },
  // The /api/* and /openapi.json → backend proxy lives in src/proxy.ts, so it
  // can read BACKEND_BASE_URL at container start instead of at build time.
  // Images and media load only from this origin (avatars come through the
  // /api proxy) or in-memory sources (avatar upload previews). Agent output can
  // carry attacker-chosen URLs, and an <img> or A2UI Image/Video that loads one
  // leaks data to that host with no click. Scripts and styles are left to the
  // browser defaults.
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: "img-src 'self' data: blob:; media-src 'self' data: blob:",
          },
        ],
      },
    ];
  },
  turbopack: {
    resolveAlias: {
      crypto: './src/lib/crypto-shim.ts',
    },
  },
};

export default nextConfig;
