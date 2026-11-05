import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { User } from "@/lib/api";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { LanguagePreference } from "./LanguagePreference";

const PATCH_URL = "http://localhost:8000/api/v1/users/user-1";

const USER = {
  id: "user-1",
  username: "alice",
  firstName: "Alice",
  lastName: "Smith",
  email: "alice@example.com",
  enabled: true,
  emailVerified: true,
  roles: [],
  groupRoles: [],
  tenantId: "tenant-1",
  language: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "user-1",
  updatedBy: "user-1",
} as User;

/** The API's success envelope around `data`. */
function ok(data: unknown) {
  return HttpResponse.json({
    meta: { requestId: "r", receivedAt: "", respondedAt: "" },
    data,
    error: null,
  });
}

function authState(impersonatedBy: User | null = null) {
  return {
    auth: {
      user: USER,
      status: "authenticated" as const,
      selectedTenantId: null,
      impersonatedUserId: impersonatedBy ? USER.id : null,
      impersonatedBy,
    },
  };
}

describe("LanguagePreference", () => {
  it("saves the chosen language onto the user in the store", async () => {
    let sent: unknown;
    server.use(
      http.patch(PATCH_URL, async ({ request }) => {
        sent = await request.json();
        return ok({ ...USER, language: "ja" });
      })
    );
    const { store } = render(<LanguagePreference user={USER} />, {
      preloadedState: authState(),
    });

    await userEvent.click(screen.getByRole("combobox", { name: "Language" }));
    await userEvent.click(screen.getByRole("option", { name: "日本語" }));

    await waitFor(() => expect(store.getState().auth.user?.language).toBe("ja"));
    expect(sent).toEqual({ language: "ja" });
  });

  it("clears the setting when following the browser", async () => {
    let sent: unknown;
    server.use(
      http.patch(PATCH_URL, async ({ request }) => {
        sent = await request.json();
        return ok(USER);
      })
    );
    render(<LanguagePreference user={{ ...USER, language: "fr" }} />, {
      preloadedState: authState(),
    });

    await userEvent.click(screen.getByRole("combobox", { name: "Language" }));
    await userEvent.click(screen.getByRole("option", { name: "Follow browser language" }));

    await waitFor(() => expect(sent).toEqual({ language: null }));
  });

  it("is disabled while impersonating", () => {
    render(<LanguagePreference user={USER} />, {
      preloadedState: authState({ ...USER, id: "admin-1" }),
    });

    expect(screen.getByRole("combobox", { name: "Language" })).toBeDisabled();
    expect(screen.getByText(/while acting as another user/)).toBeInTheDocument();
  });
});
