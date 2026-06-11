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
  // Deployed on Vercel — SSR + route handlers (waitlist, cookie-consent, ingest)
  // run as Vercel serverless functions. (Original plan was S3+CloudFront with
  // separate Lambda@Edge; pivoted to Vercel for Stage 3 PaaS deploy.)
  pageExtensions: ["ts", "tsx", "md", "mdx"],
  transpilePackages: ["@colab/ui", "@colab/design-tokens"],
  env: {
    NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL ?? "https://colabclub.net",
    NEXT_PUBLIC_BRAND_NAME: process.env.NEXT_PUBLIC_BRAND_NAME ?? "Colab",
  },
};

export default withMDX(nextConfig);
