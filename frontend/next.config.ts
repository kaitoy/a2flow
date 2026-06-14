import path from 'path';
import type { NextConfig } from 'next';

/**
 * Backend origin the API proxy forwards to. Defaults to the local dev backend.
 * Keeping the browser on the frontend origin and proxying `/api/*` makes the
 * auth cookies same-origin, so `HttpOnly` + `SameSite=Lax` work as intended.
 */
const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL ?? 'http://localhost:8000';

const nextConfig: NextConfig = {
  // Self-contained server bundle consumed by frontend/Dockerfile.
  output: 'standalone',
  outputFileTracingRoot: __dirname,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${BACKEND_BASE_URL}/api/:path*`,
      },
      {
        // FastAPI serves its OpenAPI document at the app root; expose it on the
        // frontend origin so the Scalar viewer at /api-doc can fetch it.
        source: '/openapi.json',
        destination: `${BACKEND_BASE_URL}/openapi.json`,
      },
    ];
  },
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
