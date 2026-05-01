"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { createSession } from "@/lib/api";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    createSession("user")
      .then((id) => router.replace(`/sessions/${id}`))
      .catch(() => {
        /* stays on blank page; user can retry */
      });
  }, [router]);

  return null;
}
