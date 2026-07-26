import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { SecretRefField } from "./secret-ref-field";

const KEYS_URL = "http://localhost:8000/api/v1/secrets/:secretId/keys";
const SECRETS_URL = "http://localhost:8000/api/v1/secrets";

/** Drives the controlled field the way a form would, so selections stick. */
function Harness({ initial = "", onChange }: { initial?: string; onChange?: (v: string) => void }) {
  const [value, setValue] = useState(initial);
  return (
    <SecretRefField
      value={value}
      onChange={(next) => {
        setValue(next);
        onChange?.(next);
      }}
      label="Auth Password"
      idPrefix="repoAuthPassword"
    />
  );
}

/** The secret select, named by the `label` prop through its `<label for>`. */
function secretSelect() {
  return screen.getByRole("combobox", { name: "Auth Password" });
}

/** The entry select, whose label is fixed. */
function keySelect() {
  return screen.getByRole("combobox", { name: "Entry Key" });
}

describe("SecretRefField", () => {
  it("offers every registered secret, of either type", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(secretSelect());

    expect(await screen.findByRole("option", { name: "github-token" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "vault-token" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "None" })).toBeInTheDocument();
  });

  it("disables the entry select until a secret is chosen", () => {
    render(<Harness />);
    expect(keySelect()).toBeDisabled();
  });

  it("completes the reference on its own when the secret holds one entry", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    await user.click(secretSelect());
    await user.click(await screen.findByRole("option", { name: "github-token" }));

    await waitFor(() => expect(onChange).toHaveBeenLastCalledWith("github-token/token"));
  });

  it("lets the entry be picked when a vault secret holds several", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    await user.click(secretSelect());
    await user.click(await screen.findByRole("option", { name: "vault-token" }));
    await user.click(keySelect());
    await user.click(await screen.findByRole("option", { name: "username" }));

    expect(onChange).toHaveBeenLastCalledWith("vault-token/username");
  });

  it("reports no reference when the secret is cleared", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness initial="github-token/token" onChange={onChange} />);

    await user.click(secretSelect());
    await user.click(await screen.findByRole("option", { name: "None" }));

    expect(onChange).toHaveBeenLastCalledWith("");
  });

  it("prefills both selects from a stored reference", async () => {
    render(<Harness initial="vault-token/password" />);

    await waitFor(() => expect(secretSelect()).toHaveTextContent("vault-token"));
    expect(keySelect()).toHaveTextContent("password");
  });

  it("keeps and flags a reference whose secret no longer exists", async () => {
    render(<Harness initial="gone/pat" />);

    expect(await screen.findByText(/no secret named "gone" is registered/i)).toBeInTheDocument();
    expect(secretSelect()).toHaveTextContent("gone (not found)");
  });

  it("keeps and flags an entry the secret no longer holds", async () => {
    render(<Harness initial="github-token/missing" />);

    expect(
      await screen.findByText(/secret "github-token" has no entry "missing"/i)
    ).toBeInTheDocument();
    expect(keySelect()).toHaveTextContent("missing (not found)");
  });

  it("keeps the stored entry when the keys cannot be listed", async () => {
    server.use(
      http.get(KEYS_URL, () => envelopeErr("SECRET_RESOLUTION_FAILED", "vault down", 502))
    );
    render(<Harness initial="vault-token/password" />);

    expect(await screen.findByText(/could not list the entries/i)).toBeInTheDocument();
    expect(keySelect()).toHaveTextContent("password");
  });

  it("does not brand a stored secret as missing when the list cannot be fetched", async () => {
    server.use(http.get(SECRETS_URL, () => envelopeErr("INTERNAL_ERROR", "boom", 500)));
    render(<Harness initial="github-token/token" />);

    await waitFor(() => expect(secretSelect()).toHaveTextContent("github-token"));
    expect(screen.queryByText(/not found/i)).not.toBeInTheDocument();
  });

  it("offers no entries for a secret that has none", async () => {
    const user = userEvent.setup();
    server.use(http.get(KEYS_URL, () => envelope([])));
    render(<Harness />);

    await user.click(secretSelect());
    await user.click(await screen.findByRole("option", { name: "github-token" }));
    await user.click(keySelect());

    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(1));
    expect(screen.getByRole("option", { name: "None" })).toBeInTheDocument();
  });
});
