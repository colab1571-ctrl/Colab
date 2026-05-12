import type { NextConfig } from "next";
import createMDX from "@next/mdx";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";
import rehypeAutolinkHeadings from "rehype-autolink-headings";

const withMDX = createMDX({
  options: {
    remarkPlugins: [remarkGfm],
    rehypePlugins: [rehypeSlug, rehypeAutolinkHeadings],
  },
});

const nextConfig: NextConfig = {
  // Static export — route handlers (waitlist, cookie-consent, ingest) are excluded
  // and deployed as Lambda@Edge / Fargate behind the same CloudFront distribution.
  output: "export",
  // Allow .mdx page files
  pageExtensions: ["ts", "tsx", "md", "mdx"],
  transpilePackages: ["@colab/ui", "@colab/design-tokens"],
  images: {
    // Required for static export; images are pre-optimised via sharp at build time
    unoptimized: true,
  },
  // Env vars forwarded at build time (also available via NEXT_PUBLIC_ prefix at runtime)
  env: {
    NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL ?? "https://colabclub.net",
    NEXT_PUBLIC_BRAND_NAME: process.env.NEXT_PUBLIC_BRAND_NAME ?? "<BRAND_NAME>",
  },
};

export default withMDX(nextConfig);
