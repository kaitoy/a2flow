import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { OidcSettingsFields, type OidcSettingsFieldsProps } from "./oidc-settings-fields";

/** Mounts the fields on a real form, as the Tenant Settings page does. */
function Harness(props: Pick<OidcSettingsFieldsProps, "redirectUri" | "secretSaved">) {
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
