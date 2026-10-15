import { useForm } from "react-hook-form";
import { describe, expect, it } from "vitest";
import { render, screen } from "@/test/test-utils";
import {
  emptyKnowledgeBaseFormValues,
  KnowledgeBaseFields,
  type KnowledgeBaseFormValues,
  toKnowledgeBaseBody,
} from "./knowledge-base-fields";

function Editable() {
  const {
    register,
    formState: { errors },
  } = useForm<KnowledgeBaseFormValues>({ defaultValues: emptyKnowledgeBaseFormValues() });
  return <KnowledgeBaseFields register={register} errors={errors} showPlaceholders />;
}

describe("KnowledgeBaseFields", () => {
  it("renders the name and description inputs", () => {
    render(<Editable />);
    expect(screen.getByLabelText(/name/i)).toHaveAttribute("placeholder", "e.g. IT operations");
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
  });

  it("renders values instead of controls when read-only", () => {
    render(<KnowledgeBaseFields readOnly values={{ name: "IT", description: "" }} />);
    expect(screen.getByText("IT")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("sends a blank description as null", () => {
    expect(toKnowledgeBaseBody({ name: "IT", description: "" })).toEqual({
      name: "IT",
      description: null,
    });
  });
});
