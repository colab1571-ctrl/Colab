/**
 * Waitlist form route handler stub.
 * Full implementation in spec 017 (marketing-web) — will persist to DB and send welcome email.
 */

import { type NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const formData = await request.formData();
  const email = formData.get("email");

  if (!email || typeof email !== "string" || !email.includes("@")) {
    return NextResponse.json(
      { error: "Valid email required." },
      { status: 400 }
    );
  }

  // TODO spec 017: persist to waitlist table + send SES welcome email
  console.log("[waitlist] Email submitted:", email);

  // For now, redirect back with success indicator
  return NextResponse.redirect(new URL("/?waitlist=joined", request.url));
}
