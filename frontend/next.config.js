/** @type {import('next').NextConfig} */
// The browser only ever talks to this Next.js server; /api/* is proxied to FastAPI.
// API_INTERNAL_URL is read at build time (docker: http://backend:8000, local dev: http://localhost:8000).
const API = process.env.API_INTERNAL_URL || 'http://localhost:8000';

module.exports = {
  output: 'standalone',
  reactStrictMode: true,
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${API}/api/:path*` }];
  },
};
