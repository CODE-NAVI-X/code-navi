import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
