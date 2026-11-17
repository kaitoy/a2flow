import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ApprovalBacklogEntry } from "@/lib/api";
import { BacklogGauge } from "./backlog-gauge";

const entry = (overrides: Partial<ApprovalBacklogEntry>): ApprovalBacklogEntry => ({
  groupId: null,
  groupKind: null,
  groupLabel: null,
  pending: 1,
  overThreshold: 0,
  avgWaitSeconds: 60,
  maxWaitSeconds: 60,
  ...overrides,
});

describe("BacklogGauge", () => {
  it("states the backlog, its stalled share, and the longest wait", () => {
    render(
      <BacklogGauge
        pending={4}
        overThreshold={1}
        oldestSeconds={3 * 86_400}
        entries={[]}
        userNames={new Map()}
      />
    );
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("Waiting over 24h").closest("div")).toHaveTextContent("1");
    expect(screen.getByText("Longest wait").closest("div")).toHaveTextContent("3d");
    expect(screen.getByText("Nothing is waiting for approval.")).toBeInTheDocument();
  });

  it("splits the ring into an on-time arc and a stalled arc", () => {
    const { container } = render(
      <BacklogGauge
        pending={4}
        overThreshold={1}
        oldestSeconds={90_000}
        entries={[]}
        userNames={new Map()}
      />
    );
    const arcs = [...container.querySelectorAll("circle[pathLength]")];
    expect(arcs.map((arc) => arc.getAttribute("stroke-dasharray"))).toEqual([
      "73.5 100",
      "23.5 100",
    ]);
  });

  it("names a user from the resolved names, a group by its label, and the rest as unassigned", () => {
    render(
      <BacklogGauge
        pending={3}
        overThreshold={0}
        oldestSeconds={7_200}
        entries={[
          entry({ groupId: "u1", groupKind: "user", maxWaitSeconds: 7_200, pending: 2 }),
          entry({ groupId: "g1", groupKind: "group", groupLabel: "Finance" }),
          entry({}),
        ]}
        userNames={new Map([["u1", "Alice Smith"]])}
      />
    );
    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Alice Smith");
    expect(rows[0]).toHaveTextContent("2 pending · 2h");
    expect(rows[1]).toHaveTextContent("Finance");
    expect(rows[2]).toHaveTextContent("Unassigned");
  });
});
