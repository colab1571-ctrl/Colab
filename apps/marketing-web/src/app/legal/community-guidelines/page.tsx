import type { Metadata } from "next";
import { BRAND_NAME, SITE_URL } from "../../../lib/brand";
import { MDXLayout } from "../../../components/MDXLayout";
import GuidelinesContent from "../../../../content/legal/community-guidelines.mdx";

export const metadata: Metadata = {
  title: "Community Guidelines",
  description: `${BRAND_NAME} Community Guidelines — how we expect members to treat each other.`,
  alternates: { canonical: `${SITE_URL}/legal/community-guidelines` },
  openGraph: {
    title: `Community Guidelines | ${BRAND_NAME}`,
    url: `${SITE_URL}/legal/community-guidelines`,
  },
};

export default function CommunityGuidelinesPage(): React.ReactElement {
  return (
    <MDXLayout title="Community Guidelines" lastUpdated="2026-05-11">
      <GuidelinesContent />
    </MDXLayout>
  );
}
