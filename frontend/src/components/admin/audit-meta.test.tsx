import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/msw/server";
import { AuditMeta } from "./audit-meta";

describe("AuditMeta", () => {
  it("resolves created/updated user IDs to names", async () => {
    render(
      <AuditMeta
        createdBy="user-1"
        updatedBy="user-2"
        createdAt="2026-01-02T03:04:05Z"
        updatedAt="2026-01-02T03:04:05Z"
      />
    );

    // The MSW user handler resolves every ID to USER_1 ("Alice Smith").
    await waitFor(() =>
      expect(screen.getAllByText("Alice Smith").length).toBeGreaterThanOrEqual(2)
    );
    expect(screen.getByText("Created by")).toBeInTheDocument();
    expect(screen.getByText("Updated by")).toBeInTheDocument();
    expect(screen.getByText("Created at")).toBeInTheDocument();
    expect(screen.getByText("Updated at")).toBeInTheDocument();
  });

  it("falls back to the raw ID when the user cannot be resolved", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/users/:userId", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 })
      )
    );

    render(<AuditMeta createdBy="ghost-user" updatedBy="ghost-user" />);

    await waitFor(() => expect(screen.getAllByText("ghost-user").length).toBeGreaterThanOrEqual(2));
  });
});
