/** @module AdminPage — Welcome landing page: greeting plus quick-action cards for chat and admin sections. */
import { type LucideIcon, MessageSquare } from "lucide-react";
import Link from "next/link";
import { type AdminNavItem, adminNavItems } from "@/lib/admin-nav";

/** Quick-action cards: start a chat first, then every admin destination. */
const CARDS: AdminNavItem[] = [
  {
    href: "/new-session",
    label: "Start chat",
    icon: MessageSquare,
    description: "Open a new agent conversation",
  },
  ...adminNavItems,
];

/**
 * Welcome page shown at `/admin`. Renders inside the admin shell (sidebar +
 * app bar) and greets the user with quick-action cards that link to the chat
 * and each admin section. This is the landing page reached from `/`, after
 * login, and by clicking the A2Flow logo.
 */
export default function AdminPage() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-gradient-accent">
          Welcome to A2Flow
        </h1>
        <p className="mt-2 text-sm text-on-surface-variant">
          Chat with the agent or jump straight into managing your workspace.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {CARDS.map((card) => (
          <WelcomeCard key={card.href} {...card} />
        ))}
      </div>
    </div>
  );
}

/** A single quick-action card linking to a destination with an accent icon tile. */
function WelcomeCard({
  href,
  label,
  icon: Icon,
  description,
}: {
  href: string;
  label: string;
  icon: LucideIcon;
  description: string;
}) {
  return (
    <Link
      href={href}
      className={[
        "group flex items-start gap-4 rounded-2xl glass-panel p-5",
        "transition-[transform,translate,scale,box-shadow] duration-[var(--motion-duration-base)] ease-[var(--motion-ease-standard)]",
        "hover:shadow-glow motion-safe:hover:-translate-y-0.5",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
      ].join(" ")}
    >
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl glass-panel-strong text-accent shadow-glow">
        <Icon size={22} strokeWidth={1.8} aria-hidden="true" />
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="text-base font-medium tracking-tight text-on-surface group-hover:text-accent">
          {label}
        </span>
        <span className="mt-0.5 text-sm text-on-surface-variant">{description}</span>
      </span>
    </Link>
  );
}
