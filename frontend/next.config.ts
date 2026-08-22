import type { NextConfig } from "next";

const apiProxyTarget = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  devIndicators: false,
  async rewrites() {
    return [
      {
        source: "/docs",
        destination: `${apiProxyTarget}/docs`,
      },
      {
        source: "/docs/:path*",
        destination: `${apiProxyTarget}/docs/:path*`,
      },
      {
        source: "/openapi.json",
        destination: `${apiProxyTarget}/openapi.json`,
      },
      {
        source: "/redoc",
        destination: `${apiProxyTarget}/redoc`,
      },
      {
        source: "/api/:path*",
        destination: `${apiProxyTarget}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
