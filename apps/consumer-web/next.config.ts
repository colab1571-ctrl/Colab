import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@colab/ui", "@colab/design-tokens", "@colab/i18n"],
  experimental: {
    typedRoutes: true,
  },
  async rewrites() {
    return [
      // PostHog reverse-proxy to avoid ad-blockers
      {
        source: "/ingest/static/:path*",
        destination: "https://us-assets.i.posthog.com/static/:path*",
      },
      {
        source: "/ingest/:path*",
        destination: "https://us.i.posthog.com/:path*",
      },
    ];
  },
};

export default nextConfig;
