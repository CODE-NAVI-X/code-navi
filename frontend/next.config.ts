import type { NextConfig } from "next";

const configuredDevOrigins = (process.env.CODE_NAVI_ALLOWED_DEV_ORIGINS ?? "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  // Keep `next dev` from creating untracked agent-instruction files in the
  // repository on every machine that starts the frontend.
  agentRules: false,
  // The local launcher and documentation use 127.0.0.1. Next.js otherwise
  // blocks development assets requested through that host before hydration.
  // Additional LAN hosts must be supplied explicitly for the current machine.
  allowedDevOrigins: ["127.0.0.1", "localhost", ...configuredDevOrigins],
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
