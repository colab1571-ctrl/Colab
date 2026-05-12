/**
 * /flags — Feature flag console.
 * Role: all admin roles (read); prod writes require super_admin.
 */

import { Suspense } from "react";
import { requireRole } from "@/lib/auth";
import { getFlags, type FeatureFlag } from "@/lib/admin-api";

const ENVS = ["dev", "staging", "prod"] as const;

async function FlagTable({
  userId,
  roles,
  env,
}: {
  userId: string;
  roles: string[];
  env: (typeof ENVS)[number];
}): Promise<React.ReactElement> {
  const flags = await getFlags(userId, roles, env);

  if (flags.length === 0) {
    return <p className="text-neutral-400 text-sm py-4">No flags in {env}.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-neutral-200 mb-6">
      <table className="w-full text-sm">
        <thead className="bg-neutral-100 text-xs uppercase text-neutral-500">
          <tr>
            {["Key", "Description", "Value", "Canary %", "Updated By", "Updated At"].map((h) => (
              <th key={h} className="px-4 py-3 text-left">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-100">
          {flags.map((f: FeatureFlag) => (
            <tr key={`${f.env}-${f.key}`} className="hover:bg-neutral-50">
              <td className="px-4 py-3 font-mono text-xs">{f.key}</td>
              <td className="px-4 py-3 text-neutral-600 max-w-xs truncate">{f.description}</td>
              <td className="px-4 py-3">
                <code className="bg-neutral-100 px-1.5 py-0.5 rounded text-xs">
                  {JSON.stringify(f.value)}
                </code>
              </td>
              <td className="px-4 py-3">{f.canary_pct}%</td>
              <td className="px-4 py-3 font-mono text-xs text-neutral-400">
                {f.updated_by.slice(0, 8)}
              </td>
              <td className="px-4 py-3 text-neutral-400 text-xs">
                {new Date(f.updated_at).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function FlagsPage(): Promise<React.ReactElement> {
  const session = await requireRole(["mod", "support", "billing_admin", "super_admin"]);
  const isSuperAdmin = session.roles.includes("super_admin");

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">Feature Flags</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Flags per environment. prod writes require super_admin + MFA step-up.
      </p>

      {!isSuperAdmin && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800 mb-6">
          You have read-only access. prod flag writes require super_admin.
        </div>
      )}

      {ENVS.map((env) => (
        <div key={env} className="mb-8">
          <h2 className="text-sm font-semibold uppercase text-neutral-400 mb-3 flex items-center gap-2">
            {env}
            {env === "prod" && (
              <span className="bg-red-100 text-red-700 text-xs px-1.5 py-0.5 rounded">PROD</span>
            )}
          </h2>
          <Suspense fallback={<div className="animate-pulse h-24 bg-neutral-100 rounded" />}>
            <FlagTable userId={session.userId} roles={session.roles} env={env} />
          </Suspense>
        </div>
      ))}
    </div>
  );
}
