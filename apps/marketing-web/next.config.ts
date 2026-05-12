import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export-friendly (spec 017 will refine)
  transpilePackages: ["@colab/ui", "@colab/design-tokens"],
};

export default nextConfig;
