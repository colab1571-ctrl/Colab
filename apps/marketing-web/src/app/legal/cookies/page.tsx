import type { Metadata } from "next";
import { BRAND_NAME, SITE_URL } from "../../../lib/brand";
import { MDXLayout } from "../../../components/MDXLayout";
import CookiesContent from "../../../../content/legal/cookies.mdx";

export const metadata: Metadata = {
  title: "Cookie Policy",
  description: `${BRAND_NAME} Cookie Policy — how we use cookies and similar tracking technologies.`,
  alternates: { canonical: `${SITE_URL}/legal/cookies` },
  openGraph: {
    title: `Cookie Policy | ${BRAND_NAME}`,
    url: `${SITE_URL}/legal/cookies`,
  },
};

export default function CookiesPage(): React.ReactElement {
  return (
    <MDXLayout title="Cookie Policy" lastUpdated="2026-05-11">
      <CookiesContent />
    </MDXLayout>
  );
}
