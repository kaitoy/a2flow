import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { z } from "zod";
import { render, screen } from "@/test/test-utils";
import {
  type CredentialSource,
  CredentialSourceField,
  credentialSourceSchema,
  initialCredentialSource,
  refineCredentialSource,
} from "./credential-source-field";

function Harness({
  initial = "value",
  secretRefError,
}: {
  initial?: CredentialSource;
  secretRefError?: string;
}) {
  const [source, setSource] = useState<CredentialSource>(initial);
  return (
    <CredentialSourceField
      htmlFor="token"
      label="Token"
      hint="Stored encrypted."
      binding={{
        source,
        onSourceChange: setSource,
        secretRef: "",
        onSecretRefChange: () => {},
        secretRefError,
      }}
    >
      <input id="token" />
    </CredentialSourceField>
  );
}

describe("CredentialSourceField", () => {
  it("shows the value input and its hint while a value is entered", () => {
    render(<Harness />);

    expect(screen.getByRole("tab", { name: "Enter value" })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    expect(screen.getByLabelText("Token")).toBeInTheDocument();
    expect(screen.getByText("Stored encrypted.")).toBeInTheDocument();
  });

  it("swaps the input for a secret picker when a secret is chosen", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("tab", { name: "Use a secret" }));

    expect(screen.queryByText("Stored encrypted.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Select secret…" })).toBeInTheDocument();
    expect(screen.getByText(/Read from the secret each time/)).toBeInTheDocument();
  });

  it("shows the reference's validation message under the picker", () => {
    render(<Harness initial="secret" secretRefError="credentialSource.secretRequired" />);

    expect(screen.getByText("Select a secret and an entry.")).toBeInTheDocument();
  });

  it("labels the switch with the credential it is for", () => {
    render(<Harness />);

    expect(screen.getByRole("tablist", { name: "How Token is provided" })).toBeInTheDocument();
  });
});

describe("initialCredentialSource", () => {
  it("starts on the secret only when a reference is stored", () => {
    expect(initialCredentialSource("name/key")).toBe("secret");
    expect(initialCredentialSource(null)).toBe("value");
    expect(initialCredentialSource(undefined)).toBe("value");
  });
});

describe("refineCredentialSource", () => {
  const schema = z
    .object({ source: credentialSourceSchema, ref: z.string() })
    .superRefine((values, ctx) => refineCredentialSource(values.source, values.ref, "ref", ctx));

  it("requires a reference once a secret is chosen", () => {
    expect(schema.safeParse({ source: "secret", ref: "" }).error?.issues[0]).toMatchObject({
      path: ["ref"],
      message: "credentialSource.secretRequired",
    });
    expect(schema.safeParse({ source: "secret", ref: "a/b" }).success).toBe(true);
    expect(schema.safeParse({ source: "value", ref: "" }).success).toBe(true);
  });
});
