/**
 * /moderation/queue — Moderation case queue with SLA highlights.
 * Role: mod | super_admin
 */
import { Suspense } from "react";
import { requireRole } from "@/lib/auth";
import { getModerationQueue, type CaseSummary } from "@/lib/admin-api";
import Link from "next/link";

function SlaBadge({ slaAt }: { slaAt: string }): React.ReactElement {
  const diff = new Date(slaAt).getTime() - Date.now();
  const overdue = diff < 0;
  const nearBreach = diff < 3_600_000;
  const cls = overdue
    ? "bg-red-100 text-red-800"
    : nearBreach
      ? "bg-amber-100 text-amber-800"
      : "bg-green-100 text-green-700";
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${cls}`}>
      {overdue ? "OVERDUE" : nearBreach ? "< 1h" : "OK"}
    </span>
  );
}

async function QueueTable({
  userId,
  roles,
}: {
  userId: string;
  roles: string[];
}): Promise<React.ReactElement> {
  const cases = await getModerationQueue(userId, roles);
  if (cases.length === 0) {
    return (
      <div className="text-center py-16 text-neutral-400">No open cases.</div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-neutral-200 shadow-sm">
      <table className="w-full text-sm">
        <thead className="bg-neutral-100 text-left text-xs uppercase tracking-wide text-neutral-500">
          <tr>
            {["ID", "Type", "Score", "Opened", "SLA", "Status", ""].map((h) => (
              <th key={h} className="px-4 py-3">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-100">
          {cases.map((c: CaseSummary) => (
            <tr
              key={c.id}
              className={
                new Date(c.sla_due_at).getTime() < Date.now()
                  ? "bg-red-50"
                  : "hover:bg-neutral-50"
              }
            >
              <td className="px-4 py-3 font-mono text-xs text-neutral-500">{c.id.slice(0, 8)}</td>
              <td className="px-4 py-3">{c.subject_type}</td>
              <td className="px-4 py-3">
                <span className={c.score >= 0.9 ? "text-red-600 font-bold" : c.score >= 0.7 ? "text-amber-600 font-semibold" : ""}>
                  {c.score.toFixed(2)}
                </span>
              </td>
              <td className="px-4 py-3 text-neutral-500">
                {new Date(c.opened_at).toLocaleString()}
              </td>
              <td className="px-4 py-3"><SlaBadge slaAt={c.sla_due_at} /></td>
              <td className="px-4 py-3 capitalize">{c.status}</td>
              <td className="px-4 py-3">
                <Link href={`/moderation/case/${c.id}`} className="text-blue-600 hover:underline text-xs">
                  Review →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function ModerationQueuePage(): Promise<React.ReactElement> {
  const session = await requireRole(["mod", "super_admin"]);
  return (
    <div className="p-8 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">Moderation Queue</h1>
      <p className="text-sm text-neutral-500 mb-6">Open cases sorted by priority and SLA</p>
      <Suspense fallback={<div className="animate-pulse h-40 bg-neutral-100 rounded" />}>
        <QueueTable userId={session.userId} roles={session.roles} />
      </Suspense>
    </div>
  );
}
