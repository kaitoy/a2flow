import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { render, screen } from "@/test/test-utils";
import {
  LlmModeField,
  LlmSettingsFields,
  llmShape,
  refineTenantAdminLlm,
  toLlmBody,
  toLlmFormValues,
} from "./llm-settings-fields";

function Harness({
  apiKeySaved = false,
  inherits = false,
  keyRequired,
  withTitle,
}: {
  apiKeySaved?: boolean;
  inherits?: boolean;
  keyRequired?: boolean;
  withTitle?: boolean;
}) {
  const { register } = useForm({ defaultValues: toLlmFormValues({}) });
  return (
    <LlmSettingsFields
      model={register("llmModel")}
      apiKey={register("llmApiKey")}
      apiKeySaved={apiKeySaved}
      inherits={inherits}
      keyRequired={keyRequired}
      withTitle={withTitle}
      errors={{}}
    />
  );
}

describe("toLlmFormValues", () => {
  it("starts the key blank, since it is write-only", () => {
    expect(toLlmFormValues({ llmModel: "gemini-3.8-flash" })).toEqual({
      llmModel: "gemini-3.8-flash",
      llmApiKey: "",
    });
  });

  it("starts an unset model empty", () => {
    expect(toLlmFormValues({ llmModel: null })).toEqual({ llmModel: "", llmApiKey: "" });
  });
});

describe("toLlmBody", () => {
  it("clears a blank model and leaves a blank key out, so the stored key is kept", () => {
    const body = toLlmBody({ llmModel: "  ", llmApiKey: "" });
    expect(body).toEqual({ llmModel: null });
    expect(body).not.toHaveProperty("llmApiKey");
  });

  it("sends a trimmed model and a typed key", () => {
    expect(toLlmBody({ llmModel: " gemini-3.8-flash ", llmApiKey: "sk-1" })).toEqual({
      llmModel: "gemini-3.8-flash",
      llmApiKey: "sk-1",
    });
  });
});

describe("llmShape", () => {
  it("caps the model at the backend's 200 characters, with a catalog key as the message", () => {
    expect(llmShape.llmModel.safeParse("m".repeat(200)).success).toBe(true);
    const result = llmShape.llmModel.safeParse("m".repeat(201));
    expect(result.success).toBe(false);
    expect(result.error?.issues[0].message).toBe("llm.modelTooLong");
  });
});

describe("LlmSettingsFields", () => {
  it("prints the heading and both fields", () => {
    render(<Harness />);
    expect(screen.getByRole("heading", { name: "LLM" })).toBeInTheDocument();
    expect(screen.getByLabelText("Model")).toBeInTheDocument();
    expect(screen.getByLabelText("API key")).toBeInTheDocument();
  });

  it("omits the heading when the mode field already printed it", () => {
    render(<Harness withTitle={false} />);
    expect(screen.queryByRole("heading", { name: "LLM" })).toBeNull();
  });

  it("marks a stored key without showing one", () => {
    render(<Harness apiKeySaved />);
    expect(screen.getByLabelText("API key")).toHaveAttribute(
      "placeholder",
      "Saved — leave empty to keep it"
    );
  });

  it("says what an empty field falls back to", () => {
    const { unmount } = render(<Harness />);
    expect(screen.getByText(/built-in default model/)).toBeInTheDocument();
    unmount();

    render(<Harness inherits />);
    expect(screen.getByText(/the system's model is used/)).toBeInTheDocument();
    expect(screen.getByText(/the system's key is used/)).toBeInTheDocument();
  });

  it("says a tenant admin's model needs a key of its own", () => {
    render(<Harness inherits keyRequired />);
    expect(screen.getByText(/Required when you enter a model/)).toBeInTheDocument();
    expect(screen.queryByText(/the system's key is used/)).toBeNull();
  });
});

describe("refineTenantAdminLlm", () => {
  const schema = (keySaved: boolean) =>
    z.object(llmShape).superRefine((values, ctx) => refineTenantAdminLlm(values, ctx, keySaved));

  it("requires a key with a model unless one is stored", () => {
    const result = schema(false).safeParse({ llmModel: "m1", llmApiKey: "" });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]).toMatchObject({
      path: ["llmApiKey"],
      message: "llm.apiKeyRequired",
    });
    expect(schema(true).safeParse({ llmModel: "m1", llmApiKey: "" }).success).toBe(true);
    expect(schema(false).safeParse({ llmModel: "m1", llmApiKey: "sk" }).success).toBe(true);
  });

  it("accepts both fields left empty, or a key alone", () => {
    expect(schema(false).safeParse({ llmModel: " ", llmApiKey: "" }).success).toBe(true);
    expect(schema(false).safeParse({ llmModel: "", llmApiKey: "sk" }).success).toBe(true);
  });
});

describe("LlmModeField", () => {
  it("selects the current mode and explains it", () => {
    render(<LlmModeField mode="super_admin" onModeChange={() => {}} />);
    expect(screen.getByRole("tab", { name: "Set by a Super Admin" })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    expect(screen.getByText("A Super Admin sets this tenant's LLM, below.")).toBeInTheDocument();
  });

  it("reports the mode that is picked", async () => {
    const onModeChange = vi.fn();
    render(<LlmModeField mode="system_default" onModeChange={onModeChange} />);

    await userEvent.click(screen.getByRole("tab", { name: "Set by the tenant's Admin" }));

    expect(onModeChange).toHaveBeenCalledWith("tenant_admin");
  });
});
