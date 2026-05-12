/**
 * /billing/refunds — Refund decision queue.
 * Role: billing_admin | super_admin
 */

import { Suspense } from "react";
import { requireRole } from "@/lib/auth";
import { getRefunds, decideRefund } from "@/lib/admin-api";
import { revalidatePath } from "next/cache";

type Refund = {
  id: string;
  user_id: string;
  amount_cents: number;
  currency: string;
  reason: string;
  status: string;
  created_at: string;
};

async function RefundQueue({ userId, roles }: { userId: string; roles: string[] }): Promise<React.ReactElement> {
  const refunds = (await getRefunds(userId, roles, "pending")) as Refund[];

  if (refunds.length === 0) {
    return <div className="text-center py-16 text-neutral-400">No pending refunds.</div>;
  }

  return (
    <div className="space-y-4">
      {refunds.map((r) => (
        <div key={r.id} className="rounded-lg border border-neutral-200 p-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <span className="font-mono text-xs text-neutral-400">{r.id.slice(0, 8)}</span>
              <p className="text-sm font-semibold mt-0.5">
                {(r.amount_cents / 100).toFixed(2)} {r.currency} — {r.reason}
              </p>
              <p className="text-xs text-neutral-400">{new Date(r.created_at).toLocaleString()}</p>
            </div>
          </div>

          <div className="flex gap-2">
            <form
              action={async (formData: FormData) => {
                "use server";
                const session = requireRole(["billing_admin", "super_admin"]);
                await decideRefund(
                  r.id,
                  { decision: "approve", reason: formData.get("reason") as string },
                  session.userId,
                  session.roles,
                );
                revalidatePath("/billing/refunds");
              }}
              className="flex gap-2 items-end"
            >
              <input name="reason" placeholder="Reason" className="border rounded px-2 py-1 text-xs flex-1" required />
              <button type="submit" className="bg-green-600 text-white px-3 py-1 rounded text-xs font-semibold hover:bg-green-700">
                Approve
              </button>
            </form>

            <form
              action={async (formData: FormData) => {
                "use server";
                const session = requireRole(["billing_admin", "super_admin"]);
                await decideRefund(
                  r.id,
                  { decision: "deny", reason: formData.get("reason") as string },
                  session.userId,
                  session.roles,
                );
                revalidatePath("/billing/refunds");
              }}
              className="flex gap-2 items-end"
            >
              <input name="reason" placeholder="Reason" className="border rounded px-2 py-1 text-xs flex-1" required />
              <button type="submit" className="bg-red-600 text-white px-3 py-1 rounded text-xs font-semibold hover:bg-red-700">
                Deny
              </button>
            </form>
          </div>
        </div>
      ))}
    </div>
  );
}

export default async function RefundsPage(): Promise<React.ReactElement> {
  const session = requireRole(["billing_admin", "super_admin"]);
  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">Refund Decisions</h1>
      <p className="text-sm text-neutral-500 mb-6">Pending refund requests awaiting admin decision.</p>
      <Suspense fallback={<div className="animate-pulse h-40 bg-neutral-100 rounded" />}>
        <RefundQueue userId={session.userId} roles={session.roles} />
      </Suspense>
    </div>
  );
}
