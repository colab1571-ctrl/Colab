import type { Metadata } from "next";
import { BRAND_NAME, SITE_URL } from "../../../lib/brand";
import { MDXLayout } from "../../../components/MDXLayout";
import DmcaContent from "../../../../content/legal/dmca.mdx";

export const metadata: Metadata = {
  title: "DMCA Notice & Takedown Policy",
  description: `${BRAND_NAME} DMCA notice and takedown policy for copyright infringement claims.`,
  alternates: { canonical: `${SITE_URL}/legal/dmca` },
  openGraph: {
    title: `DMCA Policy | ${BRAND_NAME}`,
    url: `${SITE_URL}/legal/dmca`,
  },
};

export default function DmcaPage(): React.ReactElement {
  return (
    <MDXLayout title="DMCA Notice & Takedown Policy" lastUpdated="2026-05-11">
      <DmcaContent />
    </MDXLayout>
  );
}
