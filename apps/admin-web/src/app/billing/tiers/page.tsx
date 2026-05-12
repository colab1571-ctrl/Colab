/**
 * /billing/tiers — Tier entitlement editor.
 * Role: billing_admin | super_admin
 */

import { Suspense } from "react";
import { requireRole } from "@/lib/auth";
import { getTiers } from "@/lib/admin-api";

const TIERS = ["free", "premium", "pro"] as const;

async function TierEditor({
  userId,
  roles,
}: {
  userId: string;
  roles: string[];
}): Promise<React.ReactElement> {
  const tiers = await getTiers(userId, roles);

  // Collect all axis keys
  const allAxes = new Set<string>();
  for (const tier of TIERS) {
    for (const key of Object.keys(tiers[tier] ?? {})) {
      allAxes.add(key);
    }
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-neutral-200">
      <table className="w-full text-sm">
        <thead className="bg-neutral-100">
          <tr>
            <th className="px-4 py-3 text-left text-xs uppercase text-neutral-500 w-48">Axis</th>
            {TIERS.map((t) => (
              <th key={t} className="px-4 py-3 text-left text-xs uppercase text-neutral-500 capitalize">
                {t}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-100">
          {[...allAxes].sort().map((axis) => (
            <tr key={axis} className="hover:bg-neutral-50">
              <td className="px-4 py-3 font-mono text-xs text-neutral-600">{axis}</td>
              {TIERS.map((t) => {
                const cell = (tiers[t] ?? {})[axis] as
                  | { value: unknown; currency: string | null; effective_at: string }
                  | undefined;
                return (
                  <td key={t} className="px-4 py-3 text-xs">
                    {cell ? (
                      <span className="font-mono">
                        {JSON.stringify(cell.value)}
                        {cell.currency ? ` ${cell.currency}` : ""}
                      </span>
                    ) : (
                      <span className="text-neutral-300">—</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function BillingTiersPage(): Promise<React.ReactElement> {
  const session = await requireRole(["billing_admin", "super_admin"]);
  return (
    <div className="p-8 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">Tier Entitlements</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Current entitlement values per tier. Changes take effect within 60s.
      </p>
      <Suspense fallback={<div className="animate-pulse h-64 bg-neutral-100 rounded" />}>
        <TierEditor userId={session.userId} roles={session.roles} />
      </Suspense>
    </div>
  );
}
