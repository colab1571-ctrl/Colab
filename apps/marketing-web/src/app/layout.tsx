import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Colab — Creative Collaboration for Artists",
  description: "Connect with fellow creators. Collaborate on real projects. Build something meaningful.",
  openGraph: {
    title: "Colab — Creative Collaboration for Artists",
    description: "The AI-powered platform for rising artists to find and collaborate with the perfect creative partners.",
    type: "website",
  },
};

export default function MarketingLayout({ children }: { children: React.ReactNode }): React.ReactElement {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-white text-neutral-900 antialiased`}>
        {children}
      </body>
    </html>
  );
}
