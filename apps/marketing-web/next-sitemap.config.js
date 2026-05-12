/** @type {import('next-sitemap').IConfig} */
module.exports = {
  siteUrl: process.env.NEXT_PUBLIC_SITE_URL || "https://colabclub.net",
  generateRobotsTxt: true,
  changefreq: "weekly",
  priority: 0.7,
  exclude: ["/api/*", "/blog/*"],
  additionalPaths: async () => [
    { loc: "/blog", priority: 0.5, changefreq: "monthly" },
    { loc: "/how-it-works", priority: 0.8, changefreq: "monthly" },
    { loc: "/faq", priority: 0.8, changefreq: "weekly" },
    { loc: "/about", priority: 0.6, changefreq: "monthly" },
    { loc: "/legal/tos", priority: 0.4, changefreq: "monthly" },
    { loc: "/legal/privacy", priority: 0.4, changefreq: "monthly" },
    { loc: "/legal/community-guidelines", priority: 0.4, changefreq: "monthly" },
    { loc: "/legal/dmca", priority: 0.3, changefreq: "monthly" },
    { loc: "/legal/cookies", priority: 0.3, changefreq: "monthly" },
  ],
  robotsTxtOptions: {
    policies: [
      { userAgent: "*", allow: "/" },
      { userAgent: "*", disallow: "/api/" },
    ],
    additionalSitemaps: [],
  },
};
