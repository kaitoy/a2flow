import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useRouter } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render } from "@/test/test-utils";
import SignupPage from "./page";

const BASE = "http://localhost:8000/api/v1/auth";

/** Answer the login-options call with sign-up offered or not. */
function offerSignup(signup: boolean) {
  server.use(
    http.get(`${BASE}/login-options`, () => envelope({ tenantName: null, sso: false, signup }))
  );
}

describe("SignupPage", () => {
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

  it("sends the visitor to /login when sign-up is not offered", async () => {
    offerSignup(false);
    render(<SignupPage />);
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
    expect(screen.queryByTestId("signup-email")).not.toBeInTheDocument();
  });

  it("submits the form and asks the visitor to check their email", async () => {
    offerSignup(true);
    const user = userEvent.setup();
    let body: Record<string, unknown> | undefined;
    server.use(
      http.post(`${BASE}/signup`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return envelope(null);
      })
    );

    render(<SignupPage />);
    await user.type(await screen.findByTestId("signup-email"), "new@example.com");
    await user.type(screen.getByTestId("signup-username"), "newbie");
    await user.type(screen.getByTestId("signup-firstName"), "New");
    await user.type(screen.getByTestId("signup-lastName"), "Bie");
    await user.type(screen.getByTestId("signup-password"), "a-long-password-1");
    await user.click(screen.getByTestId("signup-submit"));

    expect(await screen.findByTestId("signup-sent")).toHaveTextContent("new@example.com");
    expect(body).toEqual({
      email: "new@example.com",
      username: "newbie",
      firstName: "New",
      lastName: "Bie",
      password: "a-long-password-1",
    });
  });
});
