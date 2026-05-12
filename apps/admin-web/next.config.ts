import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@colab/ui", "@colab/design-tokens"],
};

export default nextConfig;
