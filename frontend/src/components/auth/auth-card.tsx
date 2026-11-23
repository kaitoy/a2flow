/** @module AuthCard — The centered card shared by the signed-out screens. */
import type { FormEvent, ReactNode } from "react";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Logo } from "@/components/ui/logo";
import { useT } from "@/i18n/provider";

/** Props for {@link AuthCard}. */
export interface AuthCardProps {
  /** The heading under the logo. */
  title: string;
  /** Renders the card as a `<form>` submitting to this handler; a `<div>` without it. */
  onSubmit?: (e: FormEvent) => void;
  /** The operator's privacy policy, linked at the foot of the card; no link when unset. */
  privacyPolicyUrl?: string | null;
  children?: ReactNode;
}

/**
 * Full-page card with the logo and a heading, used by the screens a visitor
 * sees without a session: the sign-in, sign-up, and signed-out pages. Given a
 * `privacyPolicyUrl`, it ends with a link to it that opens in a new tab.
 */
export function AuthCard({ title, onSubmit, privacyPolicyUrl, children }: AuthCardProps) {
  const t = useT();
  const className = "glass-panel flex w-full max-w-sm flex-col gap-5 rounded-2xl p-8";
  const content = (
    <>
      <div className="flex flex-col items-center gap-3">
        <Logo className="size-12" />
        <h1 className="text-center font-display text-2xl font-semibold tracking-tight text-on-surface">
          {title}
        </h1>
      </div>
      {children}
      {privacyPolicyUrl && (
        <a
          href={privacyPolicyUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="self-center text-xs text-on-surface-variant underline-offset-4 transition-colors hover:text-on-surface hover:underline"
          data-testid="auth-privacy-policy"
        >
          {t("common.privacyPolicy")}
        </a>
      )}
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
