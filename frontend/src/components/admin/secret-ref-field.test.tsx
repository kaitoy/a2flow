import type { UserEvent } from "@testing-library/user-event";
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

/** The button opening the secret picker dialog. */
function openButton() {
  return screen.getByRole("button", { name: "Select secret…" });
}

/**
 * The chip's remove button, which is the one element naming the chosen secret
 * uniquely — the dialog's radio carries the same text as its hidden label.
 */
function secretChip(name: string) {
  return screen.findByRole("button", { name: `Remove ${name}` });
}

/** The entry select, whose label is fixed. */
function keySelect() {
  return screen.getByRole("combobox", { name: "Entry Key" });
}

/** Open the picker, choose `name`, and confirm — what an operator actually does. */
async function pickSecret(user: UserEvent, name: string) {
  await user.click(openButton());
  await user.click(await screen.findByRole("radio", { name }));
  await user.click(screen.getByRole("button", { name: "Select" }));
}

describe("SecretRefField", () => {
  it("offers every registered secret, of either type, in the picker dialog", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(openButton());

    expect(await screen.findByRole("radio", { name: "github-token" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "vault-token" })).toBeInTheDocument();
  });

  it("shows a filterable Tags column instead of Type in the picker dialog", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(openButton());
    await screen.findByRole("radio", { name: "github-token" });

    expect(screen.queryByRole("button", { name: "Type" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Tags/ })).toBeInTheDocument();
  });

  it("does not open the picker until it is asked for", () => {
    render(<Harness />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });

  it("lets only one secret be chosen at a time", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(openButton());
    await user.click(await screen.findByRole("radio", { name: "github-token" }));
    await user.click(screen.getByRole("radio", { name: "vault-token" }));

    expect(screen.getByRole("radio", { name: "vault-token" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "github-token" })).not.toBeChecked();
  });

  it("shows only the select-secret button while no secret is chosen", () => {
    render(<Harness />);
    expect(openButton()).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Entry Key" })).not.toBeInTheDocument();
    expect(screen.queryByText("—")).not.toBeInTheDocument();
  });

  it("reveals the entry select once a secret is chosen", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.queryByRole("combobox", { name: "Entry Key" })).not.toBeInTheDocument();

    await pickSecret(user, "vault-token");

    expect(keySelect()).toBeInTheDocument();
    expect(keySelect()).not.toBeDisabled();
  });

  it("completes the reference on its own when the secret holds one entry", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    await pickSecret(user, "github-token");

    await waitFor(() => expect(onChange).toHaveBeenLastCalledWith("github-token/token"));
  });

  it("lets the entry be picked when a vault secret holds several", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    await pickSecret(user, "vault-token");
    await user.click(keySelect());
    await user.click(await screen.findByRole("option", { name: "username" }));

    expect(onChange).toHaveBeenLastCalledWith("vault-token/username");
  });

  it("keeps a cancelled pick out of the field", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    await user.click(openButton());
    await user.click(await screen.findByRole("radio", { name: "github-token" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onChange).not.toHaveBeenCalled();
    // The chip's remove button, not the em dash: the dialog is still mounted
    // through its leave animation, and its Description column renders an em
    // dash of its own for every secret without one.
    expect(screen.queryByRole("button", { name: /^Remove / })).not.toBeInTheDocument();
  });

  it("reports no reference when the secret is cleared", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness initial="github-token/token" onChange={onChange} />);

    await user.click(await secretChip("github-token"));

    expect(onChange).toHaveBeenLastCalledWith("");
  });

  it("prefills the chip and the entry select from a stored reference", async () => {
    render(<Harness initial="vault-token/password" />);

    expect(await secretChip("vault-token")).toBeInTheDocument();
    expect(keySelect()).toHaveTextContent("password");
  });

  it("keeps and flags a reference whose secret no longer exists", async () => {
    render(<Harness initial="gone/pat" />);

    expect(await screen.findByText(/no secret named "gone" is registered/i)).toBeInTheDocument();
    expect(screen.getByText("gone (not found)")).toBeInTheDocument();
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

  it("does not brand a stored secret as missing when it cannot be looked up", async () => {
    server.use(http.get(SECRETS_URL, () => envelopeErr("INTERNAL_ERROR", "boom", 500)));
    render(<Harness initial="github-token/token" />);

    expect(await secretChip("github-token")).toBeInTheDocument();
    expect(keySelect()).toHaveTextContent("token");
    expect(screen.queryByText(/not found/i)).not.toBeInTheDocument();
  });

  it("offers no entries for a secret that has none", async () => {
    const user = userEvent.setup();
    server.use(http.get(KEYS_URL, () => envelope([])));
    render(<Harness />);

    await pickSecret(user, "github-token");
    await user.click(keySelect());

    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(1));
    expect(screen.getByRole("option", { name: "None" })).toBeInTheDocument();
  });
});
