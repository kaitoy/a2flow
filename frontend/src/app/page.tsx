/** @module Home — Root page: immediately redirects to /new-session. */
"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/new-session");
  }, [router]);

  return null;
}
