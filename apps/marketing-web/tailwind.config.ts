import type { Config } from "tailwindcss";
import typographyPlugin from "@tailwindcss/typography";

const config: Config = {
  content: [
    "./src/**/*.{ts,tsx,mdx}",
    "./content/**/*.{md,mdx}",
    "../../packages/ui/src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: "var(--color-brand-primary)",
          secondary: "var(--color-brand-secondary)",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "-apple-system", "sans-serif"],
      },
      typography: {
        neutral: {
          css: {
            "--tw-prose-body": "#404040",
            "--tw-prose-headings": "#171717",
            "--tw-prose-links": "var(--color-brand-primary)",
            "--tw-prose-bold": "#171717",
            "--tw-prose-counters": "#737373",
            "--tw-prose-bullets": "#d4d4d4",
            "--tw-prose-hr": "#e5e5e5",
            "--tw-prose-quotes": "#171717",
            "--tw-prose-quote-borders": "var(--color-brand-primary)",
            "--tw-prose-captions": "#737373",
            "--tw-prose-code": "#171717",
            "--tw-prose-pre-code": "#e5e5e5",
            "--tw-prose-pre-bg": "#171717",
            "--tw-prose-th-borders": "#d4d4d4",
            "--tw-prose-td-borders": "#e5e5e5",
          },
        },
      },
    },
  },
  plugins: [typographyPlugin],
};

export default config;
