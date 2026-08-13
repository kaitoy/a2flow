import { A2UIActivityType } from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { A2UI_SOURCE_TOOL_CALL_ID_KEY } from "@/lib/agentActivity";
import type { User } from "@/lib/api";
import { APPROVAL_ACTIVITY_TYPE } from "@/lib/approvalTool";
import { render, screen } from "@/test/test-utils";
import {
  type SessionAvatarRendererOptions,
  useSessionAvatarRenderer,
} from "./useSessionAvatarRenderer";

vi.mock("@/components/ui/avatar", () => ({
  Avatar: ({ user }: { user: { id: string } | null }) => (
    <span data-testid="avatar" data-user={user?.id ?? "unresolved"} />
  ),
}));

vi.mock("@/components/AgentAvatar", () => ({
  AgentAvatar: () => <span data-testid="agent-avatar" />,
}));

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ label, children }: { label: string; children: React.ReactNode }) => (
    <span data-testid="tooltip" data-label={label}>
      {children}
    </span>
  ),
}));

/** Build a `User` carrying only the fields the renderer and its mocks read. */
function user(id: string, firstName: string, lastName: string): User {
  return { id, firstName, lastName } as User;
}

const OWNER = user("owner-1", "Olivia", "Owner");
const OTHER = user("dev-2", "Dana", "Developer");
const VIEWER = user("dev-3", "Vic", "Viewer");

/** Render the hook with sensible defaults, overridable per test. */
function renderer(overrides: Partial<SessionAvatarRendererOptions> = {}) {
  const { result } = renderHook(() =>
    useSessionAvatarRenderer({
      agentLabel: "my-workflow",
      ownerUserId: OWNER.id,
      messageSenders: new Map(),
      senderUsers: new Map([
        [OWNER.id, OWNER],
        [OTHER.id, OTHER],
      ]),
      locallySentMessageIds: new Set(),
      currentUser: VIEWER,
      ...overrides,
    })
  );
  return result.current;
}

/** A `user`-role message with the given id. */
function userMessage(id: string): Message {
  return { id, role: "user", content: "hi" } as Message;
}

/**
 * Render whatever the hook's callback returned.
 *
 * The callback's return type is `ReactNode`, which admits `null` (what it
 * yields for a message carrying no avatar) and `undefined`; Testing Library's
 * `render` accepts only an element. The node therefore goes through a
 * pass-through component rather than a fragment (which Biome flags as useless)
 * or a wrapper element (which would show up in `container` and break the
 * empty-DOM assertion below).
 */
function Rendered({ node }: { node: ReactNode }) {
  return node;
}

describe("useSessionAvatarRenderer", () => {
  it("labels the agent's own messages with the agent label", () => {
    const renderAvatar = renderer();
    render(
      <Rendered node={renderAvatar({ id: "m1", role: "assistant", content: "hello" } as Message)} />
    );
    expect(screen.getByTestId("agent-avatar")).toBeInTheDocument();
    expect(screen.getByTestId("tooltip")).toHaveAttribute("data-label", "my-workflow");
  });

  it("resolves an attributed user message to its recorded sender", () => {
    const renderAvatar = renderer({ messageSenders: new Map([["m1", OTHER.id]]) });
    render(<Rendered node={renderAvatar(userMessage("m1"))} />);
    expect(screen.getByTestId("avatar")).toHaveAttribute("data-user", OTHER.id);
    expect(screen.getByTestId("tooltip")).toHaveAttribute("data-label", "Dana Developer");
  });

  it("attributes a message this viewer just sent to the current user", () => {
    const renderAvatar = renderer({ locallySentMessageIds: new Set(["m1"]) });
    render(<Rendered node={renderAvatar(userMessage("m1"))} />);
    expect(screen.getByTestId("avatar")).toHaveAttribute("data-user", VIEWER.id);
  });

  it("falls back to the session owner for unattributed history", () => {
    const renderAvatar = renderer();
    render(<Rendered node={renderAvatar(userMessage("m1"))} />);
    expect(screen.getByTestId("avatar")).toHaveAttribute("data-user", OWNER.id);
  });

  it("labels an unresolvable sender as unknown", () => {
    const renderAvatar = renderer({
      messageSenders: new Map([["m1", "deleted-user"]]),
    });
    render(<Rendered node={renderAvatar(userMessage("m1"))} />);
    expect(screen.getByTestId("avatar")).toHaveAttribute("data-user", "unresolved");
    expect(screen.getByTestId("tooltip")).toHaveAttribute("data-label", "Unknown sender");
  });

  it("resolves an A2UI surface by the tool call that produced it", () => {
    const renderAvatar = renderer({ messageSenders: new Map([["tc-1", OTHER.id]]) });
    render(
      <Rendered
        node={renderAvatar({
          id: "m1",
          role: "activity",
          activityType: A2UIActivityType,
          content: { [A2UI_SOURCE_TOOL_CALL_ID_KEY]: "tc-1" },
        } as unknown as Message)}
      />
    );
    expect(screen.getByTestId("avatar")).toHaveAttribute("data-user", OTHER.id);
  });

  it("shows no avatar on a surface nobody has acted on", () => {
    const renderAvatar = renderer();
    const { container } = render(
      <Rendered
        node={renderAvatar({
          id: "m1",
          role: "activity",
          activityType: A2UIActivityType,
          content: { [A2UI_SOURCE_TOOL_CALL_ID_KEY]: "tc-1" },
        } as unknown as Message)}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("resolves an approval control to whoever decided it", () => {
    const renderAvatar = renderer({ messageSenders: new Map([["tc-approve", OTHER.id]]) });
    render(
      <Rendered
        node={renderAvatar({
          id: "tc-approve",
          role: "activity",
          activityType: APPROVAL_ACTIVITY_TYPE,
          content: { approvalId: "ap-1" },
        } as unknown as Message)}
      />
    );
    expect(screen.getByTestId("avatar")).toHaveAttribute("data-user", OTHER.id);
  });
});
