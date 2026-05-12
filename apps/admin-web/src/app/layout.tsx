import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { AuthProvider, ThemeProvider } from "@colab/ui";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Colab Admin Console",
  robots: "noindex, nofollow",
};

export default function AdminLayout({ children }: { children: React.ReactNode }): React.ReactElement {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-neutral-50 text-neutral-900 min-h-screen`}>
        <ThemeProvider defaultTheme="light">
          <AuthProvider apiBaseUrl={process.env.NEXT_PUBLIC_API_BASE_URL ?? ""}>
            {children}
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
