/** @module admin-nav — Shared admin navigation item list used by the admin sidebar and the welcome page. */
import {
  CheckCircle2,
  KeyRound,
  ListChecks,
  type LucideIcon,
  Server,
  Users,
  Wand2,
  Workflow,
} from "lucide-react";

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
}

/**
 * Admin section destinations shared between the sidebar navigation
 * (`app/admin/layout.tsx`) and the welcome page quick-action cards
 * (`app/admin/page.tsx`) so the two stay in sync.
 */
export const adminNavItems: AdminNavItem[] = [
  { href: "/admin/users", label: "Users", icon: Users, description: "Manage accounts and roles" },
  {
    href: "/admin/agent-skills",
    label: "Agent Skills",
    icon: Wand2,
    description: "Configure agent capabilities",
  },
  {
    href: "/admin/mcp-servers",
    label: "MCP Servers",
    icon: Server,
    description: "Register tool servers",
  },
  {
    href: "/admin/secrets",
    label: "Secrets",
    icon: KeyRound,
    description: "Store credentials for tools and repos",
  },
  {
    href: "/admin/workflows",
    label: "Workflows",
    icon: Workflow,
    description: "Design multi-step flows",
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
