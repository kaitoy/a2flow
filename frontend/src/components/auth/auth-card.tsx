/** @module AuthCard — The centered card shared by the signed-out screens. */
import type { FormEvent, ReactNode } from "react";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Logo } from "@/components/ui/logo";

/** Props for {@link AuthCard}. */
export interface AuthCardProps {
  /** The heading under the logo. */
  title: string;
  /** Renders the card as a `<form>` submitting to this handler; a `<div>` without it. */
  onSubmit?: (e: FormEvent) => void;
  children?: ReactNode;
}

/**
 * Full-page card with the logo and a heading, used by the screens a visitor
 * sees without a session: the sign-in page and the signed-out page.
 */
export function AuthCard({ title, onSubmit, children }: AuthCardProps) {
  const className = "glass-panel flex w-full max-w-sm flex-col gap-5 rounded-2xl p-8";
  const content = (
    <>
      <div className="flex flex-col items-center gap-3">
        <Logo className="size-12" />
        <h1 className="font-display text-2xl font-semibold tracking-tight text-on-surface">
          {title}
        </h1>
      </div>
      {children}
    </>
  );
  return (
    <main className="relative flex min-h-dvh items-center justify-center px-4">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      {onSubmit ? (
        <form onSubmit={onSubmit} className={className}>
          {content}
        </form>
      ) : (
        <div className={className}>{content}</div>
      )}
    </main>
  );
}
