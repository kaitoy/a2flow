import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useRouter } from "next/navigation";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render } from "@/test/test-utils";
import SignupVerifyPage from "./page";

const USER = {
  id: "user-9",
  username: "newbie",
  firstName: "New",
  lastName: "Bie",
  email: "new@example.com",
  enabled: true,
  emailVerified: true,
  roles: ["admin"],
  tenantId: "t-1",
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

describe("SignupVerifyPage", () => {
  let replaceMock = vi.fn<(href: string) => void>();
  beforeEach(() => {
    replaceMock = vi.fn<(href: string) => void>();
    vi.mocked(useRouter).mockReturnValue({
      push: vi.fn(),
      replace: replaceMock,
      back: vi.fn(),
      forward: vi.fn(),
      bfcacheId: "",
      prefetch: vi.fn(),
      refresh: vi.fn(),
    });
  });
  afterEach(() => {
    window.history.pushState({}, "", "/");
  });

  it("completes only when asked, then shows the tenant and continues", async () => {
    window.history.pushState({}, "", "/signup/verify#tok-123");
    const user = userEvent.setup();
    const completeSpy = vi.fn(async ({ request }: { request: Request }) => {
      expect(await request.json()).toEqual({ token: "tok-123" });
      return envelope({
        user: USER,
        tenantName: "newbie-abc123",
        tenantUrl: "https://newbie-abc123.a2.example.com",
      });
    });
    server.use(http.post("http://localhost:8000/api/v1/auth/signup/complete", completeSpy));

    render(<SignupVerifyPage />);
    const button = await screen.findByTestId("signup-complete");
    expect(completeSpy).not.toHaveBeenCalled();
    await user.click(button);

    expect(await screen.findByTestId("signup-tenant-name")).toHaveTextContent("newbie-abc123");
    expect(screen.getByText("https://newbie-abc123.a2.example.com")).toBeInTheDocument();
    expect(completeSpy).toHaveBeenCalledTimes(1);

    await user.click(screen.getByTestId("signup-continue"));
    expect(replaceMock).toHaveBeenCalledWith("/");
  });

  it("says so when the link carries no token", async () => {
    window.history.pushState({}, "", "/signup/verify");
    render(<SignupVerifyPage />);
    expect(await screen.findByTestId("signup-no-token")).toBeInTheDocument();
    expect(screen.queryByTestId("signup-complete")).not.toBeInTheDocument();
  });
});
