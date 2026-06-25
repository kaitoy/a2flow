import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { AvatarField } from "./avatar-field";

const BASE = "http://localhost:8000";

const FULL_USER = {
  id: "user-1",
  username: "alice",
  firstName: "Alice",
  lastName: "Smith",
  email: "alice@example.com",
  enabled: true,
  emailVerified: false,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
  avatarUpdatedAt: "2026-06-24T00:00:00.000Z",
};

const AVATAR_USER = { id: "user-1", username: "alice", avatarUpdatedAt: null };

beforeAll(() => {
  // jsdom doesn't implement object URLs; the field uses them for the preview.
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});

describe("AvatarField", () => {
  it("offers a choose-image button and hides remove without a custom avatar", () => {
    render(<AvatarField user={AVATAR_USER} onChange={() => {}} />);
    expect(screen.getByRole("button", { name: /choose image/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove/i })).toBeNull();
  });

  it("shows remove when the user already has a custom avatar", () => {
    render(
      <AvatarField
        user={{ ...AVATAR_USER, avatarUpdatedAt: "2026-06-24T00:00:00.000Z" }}
        onChange={() => {}}
      />
    );
    expect(screen.getByRole("button", { name: /remove/i })).toBeInTheDocument();
  });

  it("uploads a selected file and reports the updated user", async () => {
    const onChange = vi.fn();
    server.use(http.put(`${BASE}/api/v1/users/:id/avatar`, () => envelope(FULL_USER)));

    const { container } = render(<AvatarField user={AVATAR_USER} onChange={onChange} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["image-bytes"], "a.png", { type: "image/png" });
    await userEvent.upload(input, file);

    await userEvent.click(screen.getByRole("button", { name: /^upload$/i }));
    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1));
    expect(onChange.mock.calls[0][0].avatarUpdatedAt).toBe(FULL_USER.avatarUpdatedAt);
  });

  it("removes a custom avatar and reports the updated user", async () => {
    const onChange = vi.fn();
    server.use(
      http.delete(`${BASE}/api/v1/users/:id/avatar`, () =>
        envelope({ ...FULL_USER, avatarUpdatedAt: null })
      )
    );

    render(
      <AvatarField
        user={{ ...AVATAR_USER, avatarUpdatedAt: "2026-06-24T00:00:00.000Z" }}
        onChange={onChange}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: /remove/i }));
    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1));
    expect(onChange.mock.calls[0][0].avatarUpdatedAt).toBeNull();
  });
});
