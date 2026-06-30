/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  async rewrites() {
    // En dev, proxy /api vers le backend FastAPI
    return [
      { source: "/api/:path*", destination: `${process.env.API_INTERNAL_URL || "http://backend:8000"}/api/:path*` },
    ];
  },
};
module.exports = nextConfig;
