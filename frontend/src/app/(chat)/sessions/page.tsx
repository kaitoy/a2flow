/** @module SessionsIndexPage — Redirects the bare /sessions route to /sessions/new. */
import { redirect } from "next/navigation";

export default function SessionsIndexPage() {
  redirect("/sessions/new");
}
