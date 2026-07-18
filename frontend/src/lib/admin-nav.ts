/** @module admin-nav — Shared admin navigation item list used by the admin sidebar and the welcome page. */
import {
  Building2,
  CheckCircle2,
  KeyRound,
  ListChecks,
  type LucideIcon,
  Server,
  Users,
  Wand2,
  Workflow,
} from "lucide-react";
import { hasRole, Role } from "@/lib/roles";
import { useAppSelector } from "@/store/hooks";

/** A single admin navigation entry: a route, its label, and its accent icon. */
export interface AdminNavItem {
  /** Route the item links to. */
  href: string;
  /** Human-readable label shown in the sidebar and welcome card. */
  label: string;
  /** Lucide icon rendered alongside the label. */
  icon: LucideIcon;
  /** Short description shown on the welcome page card. */
  description: string;
  /**
   * Roles that may use the section's write actions. The entry is hidden from
   * users holding none of them (a `super_admin` always sees everything). An
   * entry without `roles` is visible to every signed-in user.
   */
  roles?: Role[];
}

/**
 * Admin section destinations shared between the sidebar navigation
 * (`app/admin/layout.tsx`) and the welcome page quick-action cards
 * (`app/admin/page.tsx`) so the two stay in sync.
 *
 * Entries carrying `roles` are filtered per user by {@link useVisibleAdminNavItems}.
 * Workflow Sessions and Approvals stay visible to everyone: they are read views
 * whose per-record access is enforced by the backend (session owners and
 * designated approvers).
 */
export const adminNavItems: AdminNavItem[] = [
  {
    href: "/admin/tenants",
    label: "Tenants",
    icon: Building2,
    description: "Manage tenant organizations",
    roles: [Role.SUPER_ADMIN],
  },
  {
    href: "/admin/users",
    label: "Users",
    icon: Users,
    description: "Manage accounts and roles",
    roles: [Role.ADMIN],
  },
  {
    href: "/admin/agent-skills",
    label: "Agent Skills",
    icon: Wand2,
    description: "Configure agent capabilities",
    roles: [Role.DEVELOPER],
  },
  {
    href: "/admin/mcp-servers",
    label: "MCP Servers",
    icon: Server,
    description: "Register tool servers",
    roles: [Role.DEVELOPER],
  },
  {
    href: "/admin/secrets",
    label: "Secrets",
    icon: KeyRound,
    description: "Store credentials for tools and repos",
    roles: [Role.ADMIN],
  },
  {
    href: "/admin/workflows",
    label: "Workflows",
    icon: Workflow,
    description: "Design multi-step flows",
    roles: [Role.DEVELOPER, Role.REQUESTER],
  },
  {
    href: "/admin/workflow-sessions",
    label: "Workflow Sessions",
    icon: ListChecks,
    description: "Track workflow runs",
  },
  {
    href: "/admin/approvals",
    label: "Approvals",
    icon: CheckCircle2,
    description: "Review pending approvals",
  },
];

/**
 * Return the admin nav entries the signed-in user may act on.
 *
 * Entries without `roles` are always included; the rest require the user to
 * hold at least one of the listed roles (or `super_admin`).
 */
export function useVisibleAdminNavItems(): AdminNavItem[] {
  const user = useAppSelector((s) => s.auth.user);
  return adminNavItems.filter((item) => !item.roles || hasRole(user, ...item.roles));
}
