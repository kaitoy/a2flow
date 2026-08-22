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
  // The field turns the picked file into an object URL for the preview; pin it
  // to a fixed value so the rendered src is assertable.
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});

describe("AvatarField", () => {
  it("labels itself 'Avatar' by default", () => {
    render(<AvatarField user={AVATAR_USER} onChange={() => {}} />);
    expect(screen.getByText("Avatar")).toBeInTheDocument();
  });

  it("takes a caller-supplied label where the surrounding heading already says 'avatar'", () => {
    render(<AvatarField user={AVATAR_USER} onChange={() => {}} label="Uploaded image" />);
    expect(screen.getByText("Uploaded image")).toBeInTheDocument();
    expect(screen.queryByText("Avatar")).toBeNull();
  });

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

  it("celebrates a finished upload by default, holding the button on screen for the wiggle", async () => {
    server.use(http.put(`${BASE}/api/v1/users/:id/avatar`, () => envelope(FULL_USER)));

    const { container } = render(<AvatarField user={AVATAR_USER} onChange={() => {}} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["b"], "a.png", { type: "image/png" }));
    await userEvent.click(screen.getByRole("button", { name: /^upload$/i }));

    expect(await screen.findByRole("button", { name: /uploaded!/i })).toBeInTheDocument();
  });

  it("hands off to onUploaded instead of celebrating when the caller supplies one", async () => {
    const onUploaded = vi.fn();
    server.use(http.put(`${BASE}/api/v1/users/:id/avatar`, () => envelope(FULL_USER)));

    const { container } = render(
      <AvatarField user={AVATAR_USER} onChange={() => {}} onUploaded={onUploaded} />
    );
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["b"], "a.png", { type: "image/png" }));
    await userEvent.click(screen.getByRole("button", { name: /^upload$/i }));

    await waitFor(() => expect(onUploaded).toHaveBeenCalledOnce());
    expect(screen.queryByRole("button", { name: /uploaded!/i })).toBeNull();
    // The picked file is dropped straight away, so the field is back to its
    // resting state rather than waiting out a wiggle that never plays.
    expect(screen.getByRole("button", { name: /choose image/i })).toBeInTheDocument();
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
