import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The local launcher and documentation use 127.0.0.1. Next.js otherwise
  // blocks development assets requested through that host before hydration.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    return [
      {
        source: "/student/learning",
        destination: "/learning",
      },
      {
        source: "/student/practice",
        destination: "/practice",
      },
      {
        source: "/student/research",
        destination: "/research",
      },
    ];
  },
};

export default nextConfig;
