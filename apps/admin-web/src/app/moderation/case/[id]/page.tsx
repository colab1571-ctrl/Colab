/**
 * /moderation/case/[id] — Case detail with action menu and audit history.
 * Role: mod | super_admin
 */

import { Suspense } from "react";
import { requireRole } from "@/lib/auth";
import { getCaseDetail, takeCaseAction, getAuditLog } from "@/lib/admin-api";
import { revalidatePath } from "next/cache";

const ACTION_TYPES = [
  "warn",
  "hide",
  "temp_mute_1h",
  "temp_mute_24h",
  "temp_mute_7d",
  "permanent_ban",
  "delete_account",
  "dismiss",
] as const;

type Props = { params: { id: string } };

async function CaseDetail({ id, userId, roles }: { id: string; userId: string; roles: string[] }): Promise<React.ReactElement> {
  const detail = await getCaseDetail(id, userId, roles) as Record<string, unknown>;
  return (
    <div className="grid grid-cols-3 gap-6">
      {/* Left: Subject preview */}
      <div className="col-span-1 rounded-lg border border-neutral-200 p-4">
        <h2 className="font-semibold text-sm uppercase text-neutral-500 mb-3">Subject Preview</h2>
        <pre className="text-xs bg-neutral-50 p-3 rounded overflow-auto max-h-96">
          {JSON.stringify(detail, null, 2)}
        </pre>
      </div>

      {/* Center: Scores */}
      <div className="col-span-1 rounded-lg border border-neutral-200 p-4">
        <h2 className="font-semibold text-sm uppercase text-neutral-500 mb-3">Score Breakdown</h2>
        {detail.scores_breakdown ? (
          <pre className="text-xs bg-neutral-50 p-3 rounded overflow-auto max-h-96">
            {JSON.stringify(detail.scores_breakdown, null, 2)}
          </pre>
        ) : (
          <p className="text-neutral-400 text-sm">No scores available.</p>
        )}
      </div>

      {/* Right: Action menu */}
      <div className="col-span-1 rounded-lg border border-neutral-200 p-4">
        <h2 className="font-semibold text-sm uppercase text-neutral-500 mb-3">Action</h2>
        <form
          action={async (formData: FormData) => {
            "use server";
            const session = requireRole(["mod", "super_admin"]);
            const action_type = formData.get("action_type") as string;
            const reason = formData.get("reason") as string;
            await takeCaseAction(id, { action_type, reason }, session.userId, session.roles);
            revalidatePath(`/moderation/case/${id}`);
            revalidatePath("/moderation/queue");
          }}
          className="space-y-4"
        >
          <div>
            <label className="block text-xs text-neutral-500 mb-1">Action</label>
            <select name="action_type" className="w-full border rounded px-3 py-2 text-sm">
              {ACTION_TYPES.map((a) => (
                <option key={a} value={a}>{a.replace(/_/g, " ")}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-neutral-500 mb-1">Reason (required)</label>
            <textarea
              name="reason"
              required
              maxLength={500}
              rows={4}
              className="w-full border rounded px-3 py-2 text-sm resize-none"
              placeholder="Explain the action..."
            />
          </div>
          <button
            type="submit"
            className="w-full bg-red-600 text-white py-2 px-4 rounded font-semibold text-sm hover:bg-red-700 transition"
          >
            Submit Action
          </button>
        </form>
      </div>
    </div>
  );
}

async function AuditHistory({ id, userId, roles }: { id: string; userId: string; roles: string[] }): Promise<React.ReactElement> {
  const rows = await getAuditLog(userId, roles, { target_id: id }) as Array<Record<string, unknown>>;
  return (
    <div className="mt-6 rounded-lg border border-neutral-200">
      <h2 className="font-semibold text-sm uppercase text-neutral-500 px-4 py-3 border-b border-neutral-100">
        Audit History
      </h2>
      {rows.length === 0 ? (
        <p className="text-neutral-400 text-sm p-4">No audit entries yet.</p>
      ) : (
        <ul className="divide-y divide-neutral-100 text-sm">
          {rows.map((r) => (
            <li key={r.id as string} className="px-4 py-3 flex items-center justify-between">
              <div>
                <span className="font-medium">{r.action_type as string}</span>
                <span className="text-neutral-400 ml-2 text-xs">{r.created_at as string}</span>
              </div>
              <span className="text-neutral-500 text-xs">{r.reason as string}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default async function CaseDetailPage({ params }: Props): Promise<React.ReactElement> {
  const session = requireRole(["mod", "super_admin"]);
  return (
    <div className="p-8 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Case {params.id.slice(0, 8)}</h1>
      <Suspense fallback={<div className="animate-pulse h-64 bg-neutral-100 rounded" />}>
        <CaseDetail id={params.id} userId={session.userId} roles={session.roles} />
      </Suspense>
      <Suspense fallback={<div className="animate-pulse h-32 bg-neutral-100 rounded mt-6" />}>
        <AuditHistory id={params.id} userId={session.userId} roles={session.roles} />
      </Suspense>
    </div>
  );
}
