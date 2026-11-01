import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { render, screen } from "@/test/test-utils";
import {
  refineVaultConnection,
  savedVaultMethod,
  toVaultConnectionBody,
  toVaultConnectionFormValues,
  VaultConnectionFields,
  type VaultConnectionFormValues,
  vaultConnectionShape,
} from "./vault-connection-fields";

const BLANK: VaultConnectionFormValues = toVaultConnectionFormValues({});

/** Messages the refinement reports for `values`, given the saved method. */
function issues(values: Partial<VaultConnectionFormValues>, saved: "token" | null = null) {
  const schema = z
    .object(vaultConnectionShape)
    .superRefine((v, ctx) => refineVaultConnection(v, ctx, saved));
  const result = schema.safeParse({ ...BLANK, ...values });
  return result.success ? [] : result.error.issues.map((issue) => issue.message);
}

/** Inert `register()` result for rendering the field set on its own. */
function reg(name: string) {
  return { name, onChange: async () => {}, onBlur: async () => {}, ref: () => {} };
}

describe("refineVaultConnection", () => {
  it("accepts an empty connection", () => {
    expect(issues({})).toEqual([]);
  });

  it("requires a credential unless one is saved for the same method", () => {
    const addr = { vaultAddr: "https://vault.example.com" };
    expect(issues(addr)).toEqual(["Token is required"]);
    expect(issues(addr, "token")).toEqual([]);
    expect(issues({ ...addr, vaultAuthMethod: "approle" }, "token")).toEqual([
      "Secret ID is required",
      "Role ID is required",
    ]);
  });

  it("rejects an address without a scheme", () => {
    expect(issues({ vaultAddr: "vault.example.com", vaultCredential: "t" })).toEqual([
      "Enter an http:// or https:// address",
    ]);
  });
});

describe("savedVaultMethod", () => {
  it("is the stored method only while a credential is stored", () => {
    expect(savedVaultMethod({ vaultCredentialSet: false, vaultAuthMethod: "approle" })).toBeNull();
    expect(savedVaultMethod({ vaultCredentialSet: true, vaultAuthMethod: "approle" })).toBe(
      "approle"
    );
    expect(savedVaultMethod({ vaultCredentialSet: true })).toBe("token");
  });
});

describe("toVaultConnectionBody", () => {
  it("clears everything when the address is empty", () => {
    expect(toVaultConnectionBody(BLANK)).toEqual({
      vaultAddr: null,
      vaultAuthMethod: null,
      vaultRoleId: null,
      vaultApproleMount: null,
      vaultCredential: null,
    });
  });

  it("omits a blank credential and the AppRole fields of a token login", () => {
    expect(
      toVaultConnectionBody({ ...BLANK, vaultAddr: "https://v", vaultRoleId: "stale" })
    ).toEqual({
      vaultAddr: "https://v",
      vaultAuthMethod: "token",
      vaultRoleId: null,
      vaultApproleMount: null,
    });
  });
});

describe("VaultConnectionFields", () => {
  it("shows the AppRole fields only for AppRole and reports a method change", async () => {
    const onAuthMethodChange = vi.fn();
    const props = {
      addr: reg("vaultAddr"),
      roleId: reg("vaultRoleId"),
      approleMount: reg("vaultApproleMount"),
      credential: reg("vaultCredential"),
      onAuthMethodChange,
      savedMethod: "token" as const,
      addrHint: "Where secrets come from.",
      errors: {},
    };
    const { rerender } = render(<VaultConnectionFields {...props} authMethod="token" />);
    expect(screen.getByText("Where secrets come from.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Vault Role ID")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Vault Token")).toHaveAttribute(
      "placeholder",
      "Saved — leave empty to keep it"
    );

    await userEvent.click(screen.getByRole("tab", { name: "AppRole" }));
    expect(onAuthMethodChange).toHaveBeenCalledWith("approle");

    rerender(<VaultConnectionFields {...props} authMethod="approle" />);
    expect(screen.getByLabelText("Vault Role ID")).toBeInTheDocument();
    expect(screen.getByLabelText("Vault Secret ID")).toHaveAttribute("placeholder", "");
  });

  it("leaves the address field out when no `addr` is given", () => {
    render(
      <VaultConnectionFields
        roleId={reg("vaultRoleId")}
        approleMount={reg("vaultApproleMount")}
        credential={reg("vaultCredential")}
        authMethod="token"
        onAuthMethodChange={() => {}}
        savedMethod={null}
        errors={{}}
      />
    );
    expect(screen.queryByLabelText("Vault Address")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Vault Token")).toBeInTheDocument();
  });
});
