import { zodResolver } from "@hookform/resolvers/zod";
import { render, screen } from "@testing-library/react";
import { useForm } from "react-hook-form";
import { describe, expect, it } from "vitest";
import {
  buildSecretFormSchema,
  emptySecretFormValues,
  SecretFields,
  type SecretFormValues,
  toSecretBody,
} from "./secret-fields";

const schema = buildSecretFormSchema(true);

/** Host that wires the shared fields to a real form, as both pages do. */
function Host({ defaults }: { defaults?: Partial<SecretFormValues> }) {
  const {
    register,
    control,
    watch,
    formState: { errors },
  } = useForm<SecretFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { ...emptySecretFormValues(), ...defaults },
  });
  return (
    <SecretFields register={register} control={control} errors={errors} type={watch("type")} />
  );
}

describe("SecretFields", () => {
  it("shows a description field", () => {
    render(<Host />);
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
  });

  describe("readOnly", () => {
    it("renders a set description as text", () => {
      render(
        <SecretFields
          readOnly
          values={{
            ...emptySecretFormValues(),
            name: "aws-credentials",
            description: "Used by the deploy skill",
          }}
        />
      );
      expect(screen.getByText("Used by the deploy skill")).toBeInTheDocument();
    });
  });
});

describe("toSecretBody", () => {
  it("includes a set description for a local secret", () => {
    expect(
      toSecretBody({
        ...emptySecretFormValues(),
        name: "srv",
        description: "Used by the deploy skill",
        entries: [{ key: "token", value: "x" }],
      })
    ).toEqual({
      name: "srv",
      description: "Used by the deploy skill",
      type: "local",
      entries: { token: "x" },
    });
  });

  it("sends null when the description is blank", () => {
    expect(
      toSecretBody({
        ...emptySecretFormValues(),
        name: "srv",
        entries: [{ key: "token", value: "x" }],
      })
    ).toMatchObject({ description: null });
  });

  it("includes a set description for a vault secret", () => {
    expect(
      toSecretBody({
        ...emptySecretFormValues(),
        name: "srv",
        description: "Used by the deploy skill",
        type: "vault",
        vaultMount: "secret",
        vaultPath: "myapp/aws",
      })
    ).toEqual({
      name: "srv",
      description: "Used by the deploy skill",
      type: "vault",
      vaultMount: "secret",
      vaultPath: "myapp/aws",
    });
  });
});
