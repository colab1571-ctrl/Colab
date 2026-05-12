/**
 * /support/queue — Support ticket queue with SLA timers.
 * Role: support | super_admin
 */

import { Suspense } from "react";
import { requireRole } from "@/lib/auth";
import { getSupportQueue } from "@/lib/admin-api";
import Link from "next/link";

type Ticket = {
  id: string;
  category: string;
  status: string;
  subject: string;
  opened_at: string;
  ack_sla_due_at?: string;
  resolve_sla_due_at?: string;
  user?: { handle: string; tier: string };
};

function SlaTimer({ dueAt }: { dueAt?: string }): React.ReactElement {
  if (!dueAt) return <span className="text-neutral-300">—</span>;
  const diff = new Date(dueAt).getTime() - Date.now();
  const cls =
    diff < 0
      ? "text-red-600 font-bold"
      : diff < 7_200_000
        ? "text-amber-600 font-semibold"
        : "text-green-600";
  const abs = Math.abs(diff);
  const h = Math.floor(abs / 3_600_000);
  const m = Math.floor((abs % 3_600_000) / 60_000);
  return (
    <span className={cls}>
      {diff < 0 ? "-" : ""}{h}h {m}m
    </span>
  );
}

const CATEGORY_COLORS: Record<string, string> = {
  harassment: "bg-red-100 text-red-700",
  ip: "bg-purple-100 text-purple-700",
  payment: "bg-blue-100 text-blue-700",
  technical: "bg-gray-100 text-gray-700",
  other: "bg-neutral-100 text-neutral-500",
};

async function TicketQueueTable({
  userId,
  roles,
}: {
  userId: string;
  roles: string[];
}): Promise<React.ReactElement> {
  const tickets = (await getSupportQueue(userId, roles)) as Ticket[];

  if (tickets.length === 0) {
    return (
      <div className="text-center py-16 text-neutral-400">
        No open tickets — queue is clear.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-neutral-200 shadow-sm">
      <table className="w-full text-sm">
        <thead className="bg-neutral-100 text-left text-xs uppercase tracking-wide text-neutral-500">
          <tr>
            {["ID", "Category", "User", "Subject", "Opened", "Ack SLA", "Resolve SLA", "Status", ""].map((h) => (
              <th key={h} className="px-4 py-3">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-100">
          {tickets.map((t) => (
            <tr key={t.id} className="hover:bg-neutral-50">
              <td className="px-4 py-3 font-mono text-xs text-neutral-500">{t.id.slice(0, 8)}</td>
              <td className="px-4 py-3">
                <span className={`px-2 py-0.5 rounded text-xs font-semibold ${CATEGORY_COLORS[t.category] ?? "bg-neutral-100"}`}>
                  {t.category}
                </span>
              </td>
              <td className="px-4 py-3 text-xs">{t.user?.handle ?? "—"}</td>
              <td className="px-4 py-3 max-w-xs truncate">{t.subject}</td>
              <td className="px-4 py-3 text-neutral-500 text-xs">{new Date(t.opened_at).toLocaleString()}</td>
              <td className="px-4 py-3"><SlaTimer {...(t.ack_sla_due_at != null ? { dueAt: t.ack_sla_due_at } : {})} /></td>
              <td className="px-4 py-3"><SlaTimer {...(t.resolve_sla_due_at != null ? { dueAt: t.resolve_sla_due_at } : {})} /></td>
              <td className="px-4 py-3 capitalize text-xs">{t.status}</td>
              <td className="px-4 py-3">
                <Link href={`/support/ticket/${t.id}`} className="text-blue-600 hover:underline text-xs">
                  Open →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function SupportQueuePage(): Promise<React.ReactElement> {
  const session = await requireRole(["support", "super_admin"]);
  return (
    <div className="p-8 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">Support Queue</h1>
      <p className="text-sm text-neutral-500 mb-6">Open tickets with SLA timers</p>
      <Suspense fallback={<div className="animate-pulse h-40 bg-neutral-100 rounded" />}>
        <TicketQueueTable userId={session.userId} roles={session.roles} />
      </Suspense>
    </div>
  );
}
