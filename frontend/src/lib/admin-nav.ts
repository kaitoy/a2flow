/** @module admin-nav — Shared admin navigation item list used by the admin sidebar and the welcome page. */
import {
  BookOpen,
  Building2,
  CheckCircle2,
  FlaskConical,
  KeyRound,
  ListChecks,
  type LucideIcon,
  ScrollText,
  Server,
  Settings2,
  ShieldCheck,
  Tags,
  User,
  UsersRound,
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
 * (`app/(admin)/layout.tsx`) and the welcome page quick-action cards
 * (`app/(admin)/page.tsx`) so the two stay in sync.
 *
 * Entries carrying `roles` are filtered per user by {@link useVisibleAdminNavItems}.
 */
export const adminNavItems: AdminNavItem[] = [
  {
    href: "/tenants",
    label: "common.tenants",
    icon: Building2,
    description: "lib.manageTenantOrganizations",
    roles: [Role.SUPER_ADMIN],
  },
  {
    href: "/users",
    label: "common.users",
    icon: User,
    description: "lib.manageAccountsAndRoles",
    roles: [Role.ADMIN, Role.DEVELOPER, Role.REVIEWER],
  },
  {
    href: "/user-groups",
    label: "common.userGroups",
    icon: UsersRound,
    description: "lib.grantRolesToSeveralAccountsAtOnce",
    roles: [Role.ADMIN, Role.DEVELOPER, Role.REVIEWER],
  },
  {
    href: "/tags",
    label: "common.tags",
    icon: Tags,
    description: "lib.curateTheLabelsRecordsAreClassifiedBy",
    roles: [Role.ADMIN, Role.DEVELOPER],
  },
  {
    href: "/secrets",
    label: "common.secrets",
    icon: KeyRound,
    description: "lib.storeCredentialsForToolsAndRepos",
    roles: [Role.ADMIN, Role.DEVELOPER],
  },
  {
    href: "/agent-skills",
    label: "common.agentSkills",
    icon: Wand2,
    description: "lib.configureAgentCapabilities",
    roles: [Role.DEVELOPER, Role.ADMIN, Role.REVIEWER],
  },
  {
    href: "/mcp-servers",
    label: "common.mcpServers",
    icon: Server,
    description: "lib.registerToolServers",
    roles: [Role.DEVELOPER, Role.ADMIN],
  },
  {
    href: "/mcp-tool-mocks",
    label: "common.toolMocks",
    icon: FlaskConical,
    description: "lib.stubToolsForDraftWorkflowRuns",
    roles: [Role.DEVELOPER, Role.ADMIN],
  },
  {
    href: "/knowledge-bases",
    label: "common.knowledgeBases",
    icon: BookOpen,
    description: "lib.buildWikisYourWorkflowsCanRead",
    roles: [Role.DEVELOPER, Role.ADMIN, Role.REVIEWER],
  },
  {
    href: "/workflows",
    label: "common.workflows",
    icon: Workflow,
    description: "lib.designMultiStepFlows",
    roles: [Role.DEVELOPER, Role.REVIEWER, Role.REQUESTER, Role.ADMIN],
  },
  {
    href: "/workflow-executions",
    label: "common.workflowExecutions",
    icon: ListChecks,
    description: "lib.trackWorkflowRuns",
    roles: [Role.ADMIN, Role.DEVELOPER, Role.REQUESTER, Role.APPROVER],
  },
  {
    href: "/approvals",
    label: "common.approvals",
    icon: CheckCircle2,
    description: "lib.reviewPendingApprovals",
    roles: [Role.ADMIN, Role.DEVELOPER, Role.REQUESTER, Role.APPROVER],
  },
  {
    href: "/audit",
    label: "common.auditLogs",
    icon: ScrollText,
    description: "lib.traceToolCallsImpersonationCertificatesAndMail",
    roles: [Role.ADMIN],
  },
  {
    href: "/tenant-settings",
    label: "common.tenantSettings",
    icon: ShieldCheck,
    description: "lib.setHowFailedSignInsLockAccounts",
    roles: [Role.ADMIN],
  },
  {
    href: "/system-settings",
    label: "common.systemSettings",
    icon: Settings2,
    description: "lib.configureTheMailServerNotificationsAreSent",
    roles: [Role.SUPER_ADMIN],
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
