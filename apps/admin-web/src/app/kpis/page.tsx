/**
 * /kpis — KPI rollup dashboard.
 * Role: all admin roles.
 */

import { Suspense } from "react";
import { requireRole } from "@/lib/auth";
import { getKpiRollups, type KPIRollupRow } from "@/lib/admin-api";

const METRIC_LABELS: Record<string, string> = {
  onboarding_completion: "Onboarding Completion",
  dau_split: "DAU Split (New vs Existing)",
  profile_health_dist: "Profile Health Distribution",
  request_ratio: "Request Accept/Reject Ratio",
  collab_feedback: "Collab Feedback Up-vote Ratio",
  support_csat: "Support CSAT",
  pct_reported: "% Profiles Reported",
};

function MetricCard({ key: metricKey, rows }: { key: string; rows: KPIRollupRow[] }): React.ReactElement {
  const metricRows = rows.filter((r) => r.key === metricKey).slice(0, 10);
  const label = METRIC_LABELS[metricKey] ?? metricKey;

  return (
    <div className="rounded-lg border border-neutral-200 p-4">
      <h3 className="font-semibold text-sm mb-3">{label}</h3>
      {metricRows.length === 0 ? (
        <p className="text-neutral-400 text-xs">No data yet.</p>
      ) : (
        <div className="space-y-1">
          {metricRows.slice(0, 5).map((r, i) => (
            <div key={i} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className="text-neutral-400">{r.day}</span>
                {Object.entries(r.dims ?? {}).map(([dk, dv]) => (
                  <span key={dk} className="bg-neutral-100 text-neutral-600 px-1.5 py-0.5 rounded">
                    {dk}: {dv}
                  </span>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono font-semibold">
                  {r.value !== null ? Number(r.value).toFixed(4) : "—"}
                </span>
                {r.count_n !== null && (
                  <span className="text-neutral-400">n={r.count_n.toLocaleString()}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

async function KPIDashboard({
  userId,
  roles,
}: {
  userId: string;
  roles: string[];
}): Promise<React.ReactElement> {
  // Last 7 days
  const to = new Date().toISOString().slice(0, 10);
  const from = new Date(Date.now() - 7 * 86_400_000).toISOString().slice(0, 10);
  const rows = await getKpiRollups(userId, roles, { from, to });

  return (
    <div className="grid grid-cols-2 gap-4">
      {Object.keys(METRIC_LABELS).map((key) => (
        <MetricCard key={key} rows={rows} />
      ))}
    </div>
  );
}

export default async function KpiDashboardPage(): Promise<React.ReactElement> {
  const session = requireRole(["mod", "support", "billing_admin", "super_admin"]);

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">KPI Dashboard</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Nightly rollups for the last 7 days. Computed by analytics-svc (02:00 UTC).
      </p>
      <Suspense
        fallback={
          <div className="grid grid-cols-2 gap-4">
            {[...Array(7)].map((_, i) => (
              <div key={i} className="animate-pulse h-40 bg-neutral-100 rounded-lg" />
            ))}
          </div>
        }
      >
        <KPIDashboard userId={session.userId} roles={session.roles} />
      </Suspense>
    </div>
  );
}
