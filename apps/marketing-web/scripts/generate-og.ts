/**
 * OG Image generation script.
 *
 * Generates pre-built Open Graph PNG images for all known routes.
 * Run as a prebuild step: `npm run generate-og`
 *
 * Uses @vercel/og ImageResponse API to render 1200×630 PNGs.
 * Output goes to public/og/ — referenced in each page's generateMetadata().
 *
 * NOTE: This script requires tsx to run: `pnpm tsx scripts/generate-og.ts`
 * In CI it is called before `next build`.
 *
 * Font: System Inter fallback until brand typeface is locked (Phase 5).
 */

import { ImageResponse } from "@vercel/og";
import { writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";

const BRAND_NAME = process.env.NEXT_PUBLIC_BRAND_NAME ?? "<BRAND_NAME>";
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://colabclub.net";
const BRAND_PRIMARY = "#5B5BD6";
const BRAND_SECONDARY = "#FFB454";

interface OgPageConfig {
  slug: string;
  title: string;
  subtitle: string;
}

const pages: OgPageConfig[] = [
  {
    slug: "home",
    title: `${BRAND_NAME}`,
    subtitle: "Find Your Creative Co-Founder",
  },
  {
    slug: "how-it-works",
    title: `How ${BRAND_NAME} Works`,
    subtitle: "AI-powered artist matching in 3 steps",
  },
  {
    slug: "faq",
    title: `FAQ — ${BRAND_NAME}`,
    subtitle: "Common questions about creative collaboration",
  },
  {
    slug: "about",
    title: `About ${BRAND_NAME}`,
    subtitle: "AI-powered collaboration for artists and creators",
  },
];

async function generateOgImage(page: OgPageConfig): Promise<void> {
  const image = new ImageResponse(
    {
      type: "div",
      props: {
        style: {
          width: "1200px",
          height: "630px",
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          justifyContent: "flex-end",
          background: `linear-gradient(135deg, #0f0f0f 0%, #1a1a2e 60%, ${BRAND_PRIMARY}33 100%)`,
          padding: "64px",
          fontFamily: "system-ui, -apple-system, sans-serif",
          position: "relative",
        },
        children: [
          // Brand logo mark
          {
            type: "div",
            props: {
              style: {
                position: "absolute",
                top: "56px",
                left: "64px",
                color: BRAND_PRIMARY,
                fontSize: "28px",
                fontWeight: "900",
                letterSpacing: "-0.5px",
              },
              children: BRAND_NAME,
            },
          },
          // Accent bar
          {
            type: "div",
            props: {
              style: {
                width: "64px",
                height: "6px",
                background: BRAND_SECONDARY,
                borderRadius: "3px",
                marginBottom: "24px",
              },
            },
          },
          // Title
          {
            type: "div",
            props: {
              style: {
                color: "#ffffff",
                fontSize: page.title.length > 20 ? "56px" : "72px",
                fontWeight: "900",
                lineHeight: "1.1",
                letterSpacing: "-2px",
                marginBottom: "16px",
                maxWidth: "900px",
              },
              children: page.title,
            },
          },
          // Subtitle
          {
            type: "div",
            props: {
              style: {
                color: "rgba(255,255,255,0.6)",
                fontSize: "28px",
                fontWeight: "400",
                lineHeight: "1.4",
                maxWidth: "700px",
              },
              children: page.subtitle,
            },
          },
          // Domain
          {
            type: "div",
            props: {
              style: {
                position: "absolute",
                bottom: "56px",
                right: "64px",
                color: "rgba(255,255,255,0.3)",
                fontSize: "20px",
                fontWeight: "500",
              },
              children: new URL(SITE_URL).host,
            },
          },
        ],
      },
    },
    { width: 1200, height: 630 }
  );

  const buffer = await image.arrayBuffer();
  const outDir = join(process.cwd(), "public", "og");
  await mkdir(outDir, { recursive: true });
  await writeFile(join(outDir, `${page.slug}.png`), Buffer.from(buffer));
  console.log(`[generate-og] Written: public/og/${page.slug}.png`);
}

async function main() {
  console.log("[generate-og] Generating OG images…");
  await Promise.all(pages.map(generateOgImage));
  console.log(`[generate-og] Done — ${pages.length} images written to public/og/`);
}

main().catch((err) => {
  console.error("[generate-og] Error:", err);
  process.exit(1);
});
