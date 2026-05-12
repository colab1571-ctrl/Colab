/**
 * Style Dictionary configuration for Colab design tokens.
 * Generates: CSS variables, Tailwind preset, RN/NativeWind theme, JSON snapshot.
 */

export default {
  source: ["tokens/**/*.json"],
  platforms: {
    css: {
      transformGroup: "css",
      prefix: "colab",
      buildPath: "build/css/",
      files: [
        {
          destination: "tokens.css",
          format: "css/variables",
          options: {
            selector: ":root",
            outputReferences: false,
          },
        },
      ],
    },
    tailwind: {
      transformGroup: "js",
      buildPath: "build/tailwind/",
      files: [
        {
          destination: "preset.js",
          format: "javascript/module-flat",
        },
      ],
    },
    rn: {
      transformGroup: "js",
      buildPath: "build/rn/",
      files: [
        {
          destination: "theme.ts",
          format: "javascript/module-flat",
        },
      ],
    },
    json: {
      transformGroup: "js",
      buildPath: "build/json/",
      files: [
        {
          destination: "tokens.json",
          format: "json/flat",
        },
      ],
    },
  },
};
