import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { AvatarCustomizer } from "./AvatarCustomizer";

const USER = {
  id: "user-1",
  username: "alice",
  firstName: "Alice",
  lastName: "Smith",
  email: "alice@example.com",
  enabled: true,
  emailVerified: false,
  avatarUpdatedAt: null,
  avatarConfig: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

const PATCH_URL = "http://localhost:8000/api/v1/users/:userId";

/** Override the PATCH handler to capture the request body. */
function capturePatchBody(): { current: unknown } {
  const captured: { current: unknown } = { current: undefined };
  server.use(
    http.patch(PATCH_URL, async ({ request }) => {
      captured.current = await request.json();
      return HttpResponse.json({
        meta: { requestId: "r", receivedAt: "", respondedAt: "" },
        data: USER,
        error: null,
      });
    })
  );
  return captured;
}

describe("AvatarCustomizer", () => {
  it("renders the part, color, and background sections", () => {
    const { container } = render(<AvatarCustomizer user={USER} />);
    expect(screen.getByText("Colors")).toBeInTheDocument();
    // The background section's distinctive controls (avoids the "Background"
    // text collision with a color-slot label of the same name).
    expect(screen.getByText("Transparent")).toBeInTheDocument();
    expect(screen.getByText("Custom")).toBeInTheDocument();
    // Selectable part thumbnails are rendered for the manifest's parts.
    expect(container.querySelectorAll("button[aria-pressed]").length).toBeGreaterThan(0);
  });

  it("saves an avatar config when Save is clicked", async () => {
    const captured = capturePatchBody();
    render(<AvatarCustomizer user={USER} />);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(captured.current).toBeDefined());
    expect(captured.current).toHaveProperty("avatarConfig");
  });

  it("records a part selection in the saved config", async () => {
    const captured = capturePatchBody();
    const { container } = render(<AvatarCustomizer user={USER} />);
    const partButtons = container.querySelectorAll<HTMLButtonElement>("button[aria-pressed]");
    expect(partButtons.length).toBeGreaterThan(0);
    await userEvent.click(partButtons[0]);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(captured.current).toBeDefined());
    const config = (captured.current as { avatarConfig: { selections: object } }).avatarConfig;
    expect(Object.keys(config.selections).length).toBeGreaterThan(0);
  });

  it("clears the config when Reset is clicked", async () => {
    const captured = capturePatchBody();
    render(<AvatarCustomizer user={{ ...USER, avatarConfig: { colors: { hair: "#112233" } } }} />);
    await userEvent.click(screen.getByRole("button", { name: "Reset to default" }));
    await waitFor(() => expect(captured.current).toBeDefined());
    expect((captured.current as { avatarConfig: unknown }).avatarConfig).toBeNull();
  });
});
