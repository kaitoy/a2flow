import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { OidcSettingsFields, type OidcSettingsFieldsProps } from "./oidc-settings-fields";

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
  return (
    <OidcSettingsFields
      enabled={register("oidcEnabled")}
      issuer={register("oidcIssuer")}
      clientId={register("oidcClientId")}
      clientSecret={register("oidcClientSecret")}
      groupsClaim={register("oidcGroupsClaim")}
      trustEmail={register("oidcTrustEmail")}
      {...props}
    />
  );
}

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
});
