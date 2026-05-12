/**
 * /audit — Audit log viewer.
 * super_admin: all rows. Others: own actions only.
 */

import { Suspense } from "react";
import { requireRole } from "@/lib/auth";
import { getAuditLog } from "@/lib/admin-api";

async function AuditLogTable({
  userId,
  roles,
}: {
  userId: string;
  roles: string[];
}): Promise<React.ReactElement> {
  const rows = (await getAuditLog(userId, roles)) as Array<Record<string, unknown>>;

  if (rows.length === 0) {
    return <div className="text-center py-16 text-neutral-400">No audit entries.</div>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-neutral-200">
      <table className="w-full text-sm">
        <thead className="bg-neutral-100 text-xs uppercase text-neutral-500">
          <tr>
            {["Time", "Actor", "Action", "Target Kind", "Target ID", "Reason", "IP"].map((h) => (
              <th key={h} className="px-4 py-3 text-left">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-100">
          {rows.map((r) => (
            <tr key={r.id as string} className="hover:bg-neutral-50">
              <td className="px-4 py-3 text-xs text-neutral-400">
                {new Date(r.created_at as string).toLocaleString()}
              </td>
              <td className="px-4 py-3 font-mono text-xs">
                {(r.admin_user_id as string).slice(0, 8)}
              </td>
              <td className="px-4 py-3">
                <code className="bg-neutral-100 px-1.5 py-0.5 rounded text-xs">
                  {r.action_type as string}
                </code>
              </td>
              <td className="px-4 py-3 text-xs text-neutral-500">{r.target_kind as string}</td>
              <td className="px-4 py-3 font-mono text-xs text-neutral-400">
                {(r.target_id as string).slice(0, 12)}
              </td>
              <td className="px-4 py-3 text-xs max-w-xs truncate">
                {(r.reason as string) ?? "—"}
              </td>
              <td className="px-4 py-3 text-xs text-neutral-400">{(r.ip as string) ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function AuditPage(): Promise<React.ReactElement> {
  const session = requireRole(["mod", "support", "billing_admin", "super_admin"]);
  const isSuperAdmin = session.roles.includes("super_admin");

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">Audit Log</h1>
      <p className="text-sm text-neutral-500 mb-6">
        {isSuperAdmin
          ? "All admin actions (immutable). Showing last 50."
          : "Your actions only. super_admin can see all."}
      </p>
      <Suspense fallback={<div className="animate-pulse h-64 bg-neutral-100 rounded" />}>
        <AuditLogTable userId={session.userId} roles={session.roles} />
      </Suspense>
    </div>
  );
}
