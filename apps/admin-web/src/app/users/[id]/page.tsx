/**
 * /users/[id] — User 360° composite view.
 * Role: mod | support | billing_admin | super_admin
 */

import { Suspense } from "react";
import { requireRole } from "@/lib/auth";
import { getUser360 } from "@/lib/admin-api";

type Props = { params: { id: string } };

function Panel({ title, data }: { title: string; data: unknown }): React.ReactElement {
  return (
    <div className="rounded-lg border border-neutral-200 p-4">
      <h3 className="text-xs font-semibold uppercase text-neutral-400 mb-3">{title}</h3>
      {data && typeof data === "object" && "error" in (data as Record<string, unknown>) ? (
        <p className="text-red-400 text-xs">{(data as Record<string, unknown>).error as string}</p>
      ) : (
        <pre className="text-xs bg-neutral-50 p-2 rounded overflow-auto max-h-48">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

async function User360View({
  id,
  userId,
  roles,
  reveal,
}: {
  id: string;
  userId: string;
  roles: string[];
  reveal: boolean;
}): Promise<React.ReactElement> {
  const data = (await getUser360(id, userId, roles, reveal)) as Record<string, unknown>;

  return (
    <div className="space-y-4">
      {reveal && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
          PII revealed — this action has been audit-logged.
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <Panel title="Auth" data={data.auth} />
        <Panel title="Profile" data={data.profile} />
        <Panel title="Identity" data={data.identity} />
        <Panel title="Subscription" data={data.subscription} />
        <Panel title="Credit Wallet" data={data.credit_wallet} />
        <Panel title="Last Active" data={data.last_active} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Panel title="Recent Moderation Cases" data={data.moderation_cases} />
        <Panel title="Recent Support Tickets" data={data.support_tickets} />
      </div>
    </div>
  );
}

export default async function User360Page({
  params,
  searchParams,
}: Props & { searchParams: { reveal?: string } }): Promise<React.ReactElement> {
  const session = requireRole(["mod", "support", "billing_admin", "super_admin"]);
  const reveal = searchParams.reveal === "true";

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">User 360°</h1>
          <p className="text-sm text-neutral-500 font-mono">{params.id}</p>
        </div>
        {!reveal && (
          <a
            href={`/users/${params.id}?reveal=true`}
            className="text-sm text-amber-600 border border-amber-300 px-3 py-1.5 rounded hover:bg-amber-50 transition"
          >
            Reveal PII (audit-logged)
          </a>
        )}
      </div>

      <Suspense
        fallback={
          <div className="grid grid-cols-2 gap-4">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="animate-pulse h-40 bg-neutral-100 rounded-lg" />
            ))}
          </div>
        }
      >
        <User360View
          id={params.id}
          userId={session.userId}
          roles={session.roles}
          reveal={reveal}
        />
      </Suspense>
    </div>
  );
}
