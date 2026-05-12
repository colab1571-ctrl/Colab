import type { Metadata } from "next";
import { BRAND_NAME, SITE_URL } from "../../../lib/brand";
import { MDXLayout } from "../../../components/MDXLayout";
import PrivacyContent from "../../../../content/legal/privacy.mdx";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: `Privacy Policy for ${BRAND_NAME} — how we collect, use, and protect your personal data.`,
  alternates: { canonical: `${SITE_URL}/legal/privacy` },
  openGraph: {
    title: `Privacy Policy | ${BRAND_NAME}`,
    url: `${SITE_URL}/legal/privacy`,
  },
};

export default function PrivacyPage(): React.ReactElement {
  return (
    <MDXLayout title="Privacy Policy" lastUpdated="2026-05-11">
      <PrivacyContent />
    </MDXLayout>
  );
}
