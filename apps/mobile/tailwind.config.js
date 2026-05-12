/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: "#5B5BD6",
          secondary: "#FFB454",
          accent: "#E54D2E",
        },
        neutral: {
          0: "#FFFFFF",
          50: "#F9F9F9",
          100: "#F0F0F0",
          200: "#E0E0E0",
          300: "#C8C8C8",
          400: "#A0A0A0",
          500: "#6E6E6E",
          600: "#4C4C4C",
          700: "#333333",
          800: "#1F1F1F",
          900: "#0B0B0F",
        },
        success: "#30A46C",
        warning: "#F76B15",
        error: "#E5484D",
        info: "#0091FF",
      },
      fontFamily: {
        sans: ["Inter", "System"],
      },
      spacing: {
        "tap-target": "44px",
      },
      borderRadius: {
        sm: "4px",
        md: "8px",
        lg: "12px",
        xl: "16px",
        full: "9999px",
      },
    },
  },
  plugins: [],
};
