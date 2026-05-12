/**
 * /support/ticket/[id] — Ticket detail with reply composer.
 * Role: support | super_admin
 */

import { Suspense } from "react";
import { requireRole } from "@/lib/auth";
import { getTicketDetail, replyToTicket } from "@/lib/admin-api";
import { revalidatePath } from "next/cache";
import Link from "next/link";

type Props = { params: { id: string } };

async function TicketDetail({ id, userId, roles }: { id: string; userId: string; roles: string[] }): Promise<React.ReactElement> {
  const ticket = await getTicketDetail(id, userId, roles) as Record<string, unknown>;

  return (
    <div className="grid grid-cols-3 gap-6">
      {/* Conversation timeline */}
      <div className="col-span-2">
        <div className="rounded-lg border border-neutral-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <span className="text-xs text-neutral-400">Ticket #{(ticket.id as string).slice(0, 8)}</span>
              <h2 className="text-lg font-semibold">{ticket.subject as string}</h2>
            </div>
            <span className="px-3 py-1 rounded-full bg-blue-100 text-blue-700 text-xs font-semibold capitalize">
              {ticket.status as string}
            </span>
          </div>
          <div className="space-y-4">
            {((ticket.events as unknown[]) ?? []).map((evt, i) => {
              const e = evt as Record<string, unknown>;
              return (
                <div key={i} className={`p-3 rounded-lg ${e.actor === "agent" ? "bg-blue-50 ml-8" : "bg-neutral-50 mr-8"}`}>
                  <div className="text-xs text-neutral-400 mb-1">
                    {e.actor as string} · {new Date(e.created_at as string).toLocaleString()}
                  </div>
                  <p className="text-sm">{e.body as string}</p>
                </div>
              );
            })}
          </div>

          {/* Reply composer */}
          <div className="mt-6 border-t border-neutral-100 pt-4">
            <form
              action={async (formData: FormData) => {
                "use server";
                const session = await requireRole(["support", "super_admin"]);
                const body = formData.get("body") as string;
                await replyToTicket(id, body, session.userId, session.roles);
                revalidatePath(`/support/ticket/${id}`);
              }}
              className="space-y-3"
            >
              <label className="block text-xs text-neutral-500">Reply</label>
              <textarea
                name="body"
                required
                rows={4}
                className="w-full border rounded px-3 py-2 text-sm resize-none"
                placeholder="Type your reply..."
              />
              <div className="flex gap-2">
                <button
                  type="submit"
                  className="bg-blue-600 text-white py-2 px-4 rounded font-semibold text-sm hover:bg-blue-700 transition"
                >
                  Send Reply
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>

      {/* Sidebar */}
      <div className="col-span-1 space-y-4">
        <div className="rounded-lg border border-neutral-200 p-4">
          <h3 className="text-sm font-semibold mb-3">User</h3>
          <div className="text-sm space-y-1">
            <p className="text-neutral-600">{ticket.user_id as string}</p>
            <Link href={`/users/${ticket.user_id as string}`} className="text-blue-600 hover:underline text-xs">
              View User 360° →
            </Link>
          </div>
        </div>

        <div className="rounded-lg border border-neutral-200 p-4">
          <h3 className="text-sm font-semibold mb-3">Actions</h3>
          <div className="space-y-2">
            <form action={async () => {
              "use server";
              await requireRole(["support", "super_admin"]);
              // escalate
              revalidatePath(`/support/ticket/${id}`);
            }}>
              <button type="submit" className="w-full text-left text-sm text-amber-600 hover:text-amber-800">
                Escalate
              </button>
            </form>
            <form action={async () => {
              "use server";
              await requireRole(["support", "super_admin"]);
              // resolve
              revalidatePath(`/support/ticket/${id}`);
            }}>
              <button type="submit" className="w-full text-left text-sm text-green-600 hover:text-green-800">
                Resolve
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

export default async function TicketDetailPage({ params }: Props): Promise<React.ReactElement> {
  const session = await requireRole(["support", "super_admin"]);
  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-6">
        <Link href="/support/queue" className="text-sm text-neutral-500 hover:text-neutral-700">
          ← Back to queue
        </Link>
      </div>
      <Suspense fallback={<div className="animate-pulse h-96 bg-neutral-100 rounded" />}>
        <TicketDetail id={params.id} userId={session.userId} roles={session.roles} />
      </Suspense>
    </div>
  );
}
