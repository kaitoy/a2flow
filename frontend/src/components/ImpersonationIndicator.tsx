/** @module ImpersonationIndicator — Header chip shown while acting as another user. */
"use client";

import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { stopImpersonation } from "@/lib/api";
import { persistImpersonatedUserId } from "@/lib/impersonation";
import { clearImpersonation, setMe } from "@/store/authSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

/**
 * Header chip shown whenever an admin/super_admin is impersonating another
 * user, naming the effective user and offering a one-click way to stop.
 * Renders nothing when no impersonation is active.
 */
export function ImpersonationIndicator() {
  const dispatch = useAppDispatch();
  const router = useRouter();
  const user = useAppSelector((s) => s.auth.user);
  const impersonatedBy = useAppSelector((s) => s.auth.impersonatedBy);
  const [pending, setPending] = useState(false);

  if (!impersonatedBy || !user) return null;

  async function handleStop() {
    setPending(true);
    try {
      const me = await stopImpersonation();
      dispatch(setMe(me));
      persistImpersonatedUserId(null);
    } catch {
      // Even if the request failed, don't leave the admin stuck impersonating
      // in the UI -- clear local state and let the next request reconcile it.
      dispatch(clearImpersonation());
      persistImpersonatedUserId(null);
    } finally {
      setPending(false);
      router.push("/admin");
    }
  }

  return (
    <div className="flex items-center gap-1.5">
      <Badge>Acting as {user.username}</Badge>
      <Tooltip label="Stop impersonating">
        <button
          type="button"
          aria-label="Stop impersonating"
          onClick={handleStop}
          disabled={pending}
          className="glass-panel flex size-8 shrink-0 items-center justify-center rounded-lg cursor-pointer text-on-surface-variant transition-[background-color,border-color,color,transform,translate,scale] duration-[var(--motion-duration-fast)] ease-[var(--motion-ease-standard)] hover:border-error/40 hover:bg-error/10 hover:text-error motion-safe:hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-error/50 disabled:cursor-default disabled:opacity-50"
        >
          <LogOut
            aria-hidden="true"
            className={pending ? "size-4 motion-safe:animate-spin" : "size-4"}
          />
        </button>
      </Tooltip>
    </div>
  );
}
