/** @module AdminPage — Admin index: redirects to /admin/agent-skills. */
import { redirect } from "next/navigation";

export default function AdminPage() {
  redirect("/admin/agent-skills");
}
