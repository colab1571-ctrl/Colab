/**
 * /billing — Billing admin landing.
 * Redirects to tiers by default.
 */
import { redirect } from "next/navigation";

export default function BillingPage(): never {
  redirect("/billing/tiers");
}
