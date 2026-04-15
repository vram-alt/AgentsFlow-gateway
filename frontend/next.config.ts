import type { NextConfig } from "next";

const internalApiBase =
  process.env.INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      {
        source: "/api/policies",
        destination: `${internalApiBase}/api/policies/`,
      },
      {
        source: "/api/providers",
        destination: `${internalApiBase}/api/providers/`,
      },
      {
        source: "/api/logs",
        destination: `${internalApiBase}/api/logs/`,
      },
      {
        source: "/api/configs",
        destination: `${internalApiBase}/api/configs/`,
      },
      {
        source: "/api/configs/",
        destination: `${internalApiBase}/api/configs/`,
      },
      {
        source: "/api/:path*",
        destination: `${internalApiBase}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${internalApiBase}/health`,
      },
    ];
  },
};

export default nextConfig;
