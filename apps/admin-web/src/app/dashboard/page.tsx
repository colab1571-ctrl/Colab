export default function DashboardPage(): React.ReactElement {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-neutral-900 mb-6">Admin Dashboard</h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {[
          { label: "Moderation Queue", href: "/moderation/queue", count: "—" },
          { label: "Support Queue", href: "/support/queue", count: "—" },
          { label: "Active Users", href: "/users", count: "—" },
        ].map(({ label, href, count }) => (
          <a
            key={href}
            href={href}
            className="block bg-white border border-neutral-200 rounded-lg p-6 hover:border-brand-primary transition-colors"
          >
            <div className="text-2xl font-bold text-neutral-900 mb-1">{count}</div>
            <div className="text-sm text-neutral-500">{label}</div>
          </a>
        ))}
      </div>
      <p className="text-xs text-neutral-400 mt-8">
        Dashboard metrics wired in P15 (admin-svc + analytics-svc).
      </p>
    </div>
  );
}
