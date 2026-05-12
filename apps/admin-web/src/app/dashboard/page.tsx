import React from "react";

const dashboardLinks = [
  { label: "Moderation Queue", href: "/moderation/queue", count: "—", description: "Pending content moderation cases" },
  { label: "Support Queue", href: "/support/queue", count: "—", description: "Open support tickets awaiting response" },
  { label: "Active Users", href: "/users", count: "—", description: "Total active user accounts" },
] as const;

export default function DashboardPage(): React.ReactElement {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-neutral-900 mb-6">Admin Dashboard</h1>
      <nav aria-label="Dashboard quick links">
        <ul className="grid grid-cols-1 md:grid-cols-3 gap-6 list-none m-0 p-0">
          {dashboardLinks.map(({ label, href, count, description }) => (
            <li key={href}>
              <a
                href={href}
                className="block bg-white border border-neutral-200 rounded-lg p-6 hover:border-brand-primary transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-primary"
                aria-label={`${label}: ${count}. ${description}. Navigate to ${label}.`}
              >
                <div
                  className="text-2xl font-bold text-neutral-900 mb-1"
                  aria-hidden="true"
                >
                  {count}
                </div>
                <div className="text-sm text-neutral-500" aria-hidden="true">
                  {label}
                </div>
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <p className="text-xs text-neutral-400 mt-8">
        Dashboard metrics wired in P15 (admin-svc + analytics-svc).
      </p>
    </div>
  );
}
