import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";
import type { CredentialSource } from "@/components/admin/credential-source-field";
import { render, screen, waitFor } from "@/test/test-utils";
import {
  type OidcFormValues,
  OidcSettingsFields,
  type OidcSettingsFieldsProps,
  toOidcBody,
  toOidcFormValues,
} from "./oidc-settings-fields";

/** Mounts the fields on a real form, as the Admin Settings page does. */
function Harness(
  props: Pick<OidcSettingsFieldsProps, "redirectUri" | "subdomainRedirectUri" | "secretSaved">
) {
  const { register } = useForm({
    defaultValues: {
      oidcEnabled: false,
      oidcIssuer: "",
      oidcClientId: "",
      oidcClientSecret: "",
      oidcGroupsClaim: "groups",
      oidcTrustEmail: false,
    },
  });
  const [source, setSource] = useState<CredentialSource>("value");
  return (
    <OidcSettingsFields
      enabled={register("oidcEnabled")}
      issuer={register("oidcIssuer")}
      clientId={register("oidcClientId")}
      clientSecret={register("oidcClientSecret")}
      groupsClaim={register("oidcGroupsClaim")}
      trustEmail={register("oidcTrustEmail")}
      secretSource={{
        source,
        onSourceChange: setSource,
        secretRef: "",
        onSecretRefChange: () => {},
      }}
      {...props}
    />
  );
}

/** Form values of a configured tenant, overridable per test. */
function values(overrides: Partial<OidcFormValues> = {}): OidcFormValues {
  return {
    ...toOidcFormValues({ oidcIssuer: "https://idp", oidcClientId: "a2flow" }),
    ...overrides,
  };
}

describe("toOidcFormValues", () => {
  it("starts on the secret when the client secret is referenced", () => {
    expect(toOidcFormValues({ oidcClientSecretRef: "idp/secret" })).toMatchObject({
      oidcClientSecretSource: "secret",
      oidcClientSecretRef: "idp/secret",
    });
    expect(toOidcFormValues({})).toMatchObject({
      oidcClientSecretSource: "value",
      oidcClientSecretRef: "",
    });
  });
});

describe("toOidcBody", () => {
  it("sends only the reference when the client secret comes from a secret", () => {
    const body = toOidcBody(
      values({
        oidcClientSecret: "typed",
        oidcClientSecretSource: "secret",
        oidcClientSecretRef: "idp/secret",
      })
    );
    expect(body.oidcClientSecretRef).toBe("idp/secret");
    expect(body).not.toHaveProperty("oidcClientSecret");
  });

  it("clears the reference when the client secret is entered", () => {
    const body = toOidcBody(values({ oidcClientSecret: "typed" }));
    expect(body).toMatchObject({ oidcClientSecret: "typed", oidcClientSecretRef: null });
  });
});

const URI = "https://a2flow.example.com/api/v1/auth/oidc/callback";

describe("OidcSettingsFields", () => {
  it("shows the redirect URI and copies it", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    const { store } = render(<Harness redirectUri={URI} secretSaved={false} />);

    expect(screen.getByText(URI)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Copy" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(URI));
    expect(store.getState().toast.items.at(-1)).toMatchObject({ variant: "success" });
  });

  it("shows the tenant-address redirect URI with its own copy button", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    const sub = "https://acme.a2flow.example.com/api/v1/auth/oidc/callback";
    render(<Harness redirectUri={URI} subdomainRedirectUri={sub} secretSaved={false} />);

    expect(screen.getByText(sub)).toBeInTheDocument();
    expect(screen.getByText("Redirect URI (tenant address)")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Copy" })[1]);
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(sub));
  });

  it("omits the tenant-address redirect URI when there is none", () => {
    render(<Harness redirectUri={URI} subdomainRedirectUri={null} secretSaved={false} />);

    expect(screen.queryByText("Redirect URI (tenant address)")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Copy" })).toHaveLength(1);
  });

  it("warns that the base URL must be set when there is no redirect URI", () => {
    render(<Harness redirectUri={null} secretSaved={false} />);

    expect(screen.getByText(/base URL is not set/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy" })).not.toBeInTheDocument();
  });

  it("keeps the client secret empty and marks it saved when one is stored", () => {
    render(<Harness redirectUri={URI} secretSaved />);

    const secret = screen.getByLabelText("Client secret");
    expect(secret).toHaveValue("");
    expect(secret).toHaveAttribute("placeholder", expect.stringMatching(/^Saved/));
  });

  it("swaps the client secret input for a secret picker", async () => {
    const user = userEvent.setup();
    render(<Harness redirectUri={URI} secretSaved={false} />);

    await user.click(screen.getByRole("tab", { name: "Use a secret" }));

    expect(screen.queryByLabelText("Client secret")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Select secret…" })).toBeInTheDocument();
  });
});
