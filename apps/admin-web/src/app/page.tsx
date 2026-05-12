import { redirect } from "next/navigation";

export default function AdminRootPage(): never {
  redirect("/dashboard");
}
