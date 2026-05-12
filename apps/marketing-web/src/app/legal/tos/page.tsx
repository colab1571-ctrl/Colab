import type { Metadata } from "next";
import { BRAND_NAME, SITE_URL } from "../../../lib/brand";
import { MDXLayout } from "../../../components/MDXLayout";
import TosContent from "../../../../content/legal/tos.mdx";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: `Terms of Service for ${BRAND_NAME} — the AI-powered creative collaboration platform.`,
  alternates: { canonical: `${SITE_URL}/legal/tos` },
  openGraph: {
    title: `Terms of Service | ${BRAND_NAME}`,
    url: `${SITE_URL}/legal/tos`,
  },
};

export default function TosPage(): React.ReactElement {
  return (
    <MDXLayout title="Terms of Service" lastUpdated="2026-05-11">
      <TosContent />
    </MDXLayout>
  );
}
