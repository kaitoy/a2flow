import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { DEVELOPER, SUPER_ADMIN } from "@/test/auth-state";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
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

  it("lays out the fields as a fixed two-column grid, pairing at/by rows", async () => {
    const { container } = render(
      <AuditMeta
        createdBy="user-1"
        updatedBy="user-2"
        createdAt="2026-01-02T03:04:05Z"
        updatedAt="2026-01-02T03:04:05Z"
      />
    );

    await waitFor(() =>
      expect(screen.getAllByText("Alice Smith").length).toBeGreaterThanOrEqual(2)
    );

    const dl = container.querySelector("dl");
    expect(dl).toHaveClass("grid", "grid-cols-2");
    expect(Array.from(dl?.querySelectorAll("dt") ?? []).map((dt) => dt.textContent)).toEqual([
      "Created at",
      "Created by",
      "Updated at",
      "Updated by",
    ]);
  });

  it("shows the tenant first when tenantId is passed", async () => {
    // The MSW tenant handler resolves "tenant-1" to TENANT_1 ("Acme Corp").
    // Only a super_admin ever resolves tenant names, so the viewer must be one.
    const { container } = render(
      <AuditMeta
        createdBy="user-1"
        updatedBy="user-2"
        createdAt="2026-01-02T03:04:05Z"
        updatedAt="2026-01-02T03:04:05Z"
        tenantId="tenant-1"
      />,
      { preloadedState: SUPER_ADMIN }
    );

    await waitFor(() => expect(screen.getByText("Acme Corp")).toBeInTheDocument());

    const dl = container.querySelector("dl");
    expect(Array.from(dl?.querySelectorAll("dt") ?? []).map((dt) => dt.textContent)).toEqual([
      "Tenant",
      "Created at",
      "Created by",
      "Updated at",
      "Updated by",
    ]);
  });

  it("omits the Tenant field when tenantId is not passed", () => {
    const { container } = render(<AuditMeta createdBy="user-1" updatedBy="user-2" />);
    expect(screen.queryByText("Tenant")).not.toBeInTheDocument();
    const dl = container.querySelector("dl");
    expect(Array.from(dl?.querySelectorAll("dt") ?? []).map((dt) => dt.textContent)).not.toContain(
      "Tenant"
    );
  });

  it("falls back to the raw tenant id when the tenant cannot be resolved", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/tenants", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 })
      )
    );

    render(<AuditMeta createdBy="user-1" updatedBy="user-2" tenantId="ghost-tenant" />, {
      preloadedState: SUPER_ADMIN,
    });

    await waitFor(() => expect(screen.getByText("ghost-tenant")).toBeInTheDocument());
  });

  it("never looks the tenant up for a non-super_admin viewer, showing the raw id", async () => {
    let called = false;
    server.use(
      http.get("http://localhost:8000/api/v1/tenants", () => {
        called = true;
        return envelope([]);
      })
    );

    render(<AuditMeta createdBy="user-1" updatedBy="user-2" tenantId="tenant-1" />, {
      preloadedState: DEVELOPER,
    });

    await waitFor(() => expect(screen.getByText("tenant-1")).toBeInTheDocument());
    expect(called).toBe(false);
  });

  it("falls back to the raw ID when the user cannot be resolved", async () => {
    server.use(
      http.post("http://localhost:8000/api/v1/users/resolve-names", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 })
      )
    );

    render(<AuditMeta createdBy="ghost-user" updatedBy="ghost-user" />);

    await waitFor(() => expect(screen.getAllByText("ghost-user").length).toBeGreaterThanOrEqual(2));
  });

  it("resolves both audit IDs in one request, de-duplicating a shared ID", async () => {
    const requests: string[][] = [];
    server.use(
      http.post("http://localhost:8000/api/v1/users/resolve-names", async ({ request }) => {
        const { ids } = (await request.json()) as { ids: string[] };
        requests.push(ids);
        return envelope(ids.map((id) => ({ id, displayName: "Alice Smith" })));
      })
    );

    render(<AuditMeta createdBy="user-1" updatedBy="user-1" />);

    await waitFor(() => expect(screen.getAllByText("Alice Smith").length).toBe(2));
    expect(requests).toEqual([["user-1"]]);
  });
});
