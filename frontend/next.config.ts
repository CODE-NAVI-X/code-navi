import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The local launcher and documentation use 127.0.0.1. Next.js otherwise
  // blocks development assets requested through that host before hydration.
  // 192.168.0.32 is this machine's LAN address — used when exposing the dev
  // server to other devices on the network.
  allowedDevOrigins: ["127.0.0.1", "localhost", "192.168.0.32"],
  // Standalone output: Dockerfile.frontend copies .next/standalone and runs
  // `node server.js` — no `next start` dependency inside the container.
  output: "standalone",
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
