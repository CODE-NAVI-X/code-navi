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
  async redirects() {
    return [
      {
        source: "/workspaces",
        destination: "/",
        permanent: false,
      },
      {
        source: "/practice",
        destination: "/learning/practice",
        permanent: false,
      },
      {
        source: "/student/practice",
        destination: "/learning/practice",
        permanent: false,
      },
      {
        source: "/portrait",
        destination: "/learning/portrait",
        permanent: false,
      },
      {
        source: "/student/portrait",
        destination: "/learning/portrait",
        permanent: false,
      },
      {
        source: "/learning/explore",
        destination: "/learning",
        permanent: false,
      },
      {
        source: "/student/explore",
        destination: "/learning",
        permanent: false,
      },
      {
        source: "/notebook",
        destination: "/learning/notebook",
        permanent: false,
      },
      {
        source: "/student/notebook",
        destination: "/learning/notebook",
        permanent: false,
      },
      {
        source: "/student/learning",
        destination: "/learning",
        permanent: false,
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/student/research",
        destination: "/research",
      },
    ];
  },
};

export default nextConfig;
