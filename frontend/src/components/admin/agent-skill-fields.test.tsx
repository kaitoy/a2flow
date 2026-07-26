import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { describe, expect, it } from "vitest";
import { render, screen } from "@/test/test-utils";
import {
  AgentSkillFields,
  type AgentSkillFormValues,
  agentSkillFormSchema,
  emptyAgentSkillFormValues,
  toAgentSkillCreateBody,
  toAgentSkillUpdateBody,
} from "./agent-skill-fields";

const FILLED: AgentSkillFormValues = {
  name: "code-review",
  repoUrl: "https://github.com/owner/repo",
  repoPath: "skills/review",
  repoRef: "release/v2",
  description: "Reviews code",
  repoAuthPassword: "github-token/token",
  repoAuthUsername: "octocat",
};

/** Renders the field set inside a real form, the way both pages do. */
function Harness({ showPlaceholders = false }: { showPlaceholders?: boolean }) {
  const {
    register,
    control,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(agentSkillFormSchema),
    defaultValues: emptyAgentSkillFormValues(),
  });
  return (
    <AgentSkillFields
      register={register}
      control={control}
      errors={errors}
      showPlaceholders={showPlaceholders}
    />
  );
}

describe("emptyAgentSkillFormValues", () => {
  it("starts every field blank", () => {
    expect(emptyAgentSkillFormValues()).toEqual({
      name: "",
      repoUrl: "",
      repoPath: "",
      repoRef: "",
      description: "",
      repoAuthPassword: "",
      repoAuthUsername: "",
    });
  });
});

describe("toAgentSkillCreateBody", () => {
  it("passes every filled field through", () => {
    expect(toAgentSkillCreateBody(FILLED)).toEqual({
      name: "code-review",
      repoUrl: "https://github.com/owner/repo",
      repoPath: "skills/review",
      repoRef: "release/v2",
      description: "Reviews code",
      repoAuthPassword: "github-token/token",
      repoAuthUsername: "octocat",
    });
  });

  it("omits blank optional fields so the backend applies its defaults", () => {
    const body = toAgentSkillCreateBody({
      ...emptyAgentSkillFormValues(),
      name: "x",
      repoUrl: "https://x.com",
    });
    expect(body).toEqual({
      name: "x",
      repoUrl: "https://x.com",
      repoPath: undefined,
      repoRef: null,
      description: null,
      repoAuthPassword: undefined,
      repoAuthUsername: undefined,
    });
  });
});

describe("toAgentSkillUpdateBody", () => {
  it("sends blank optional fields as null so they are cleared", () => {
    const body = toAgentSkillUpdateBody({
      ...emptyAgentSkillFormValues(),
      name: "x",
      repoUrl: "https://x.com",
    });
    expect(body).toEqual({
      name: "x",
      repoUrl: "https://x.com",
      repoPath: "",
      repoRef: null,
      description: null,
      repoAuthPassword: null,
      repoAuthUsername: null,
    });
  });

  it("passes every filled field through", () => {
    expect(toAgentSkillUpdateBody(FILLED)).toEqual(FILLED);
  });
});

describe("AgentSkillFields", () => {
  it("renders every editable field", () => {
    render(<Harness />);
    expect(screen.getByLabelText(/^name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/repo url/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/repo path/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^ref$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/auth username/i)).toBeInTheDocument();
  });

  it("renders the auth password as a secret picker, not a text box", () => {
    render(<Harness />);
    expect(screen.getByRole("combobox", { name: "Auth Password" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Entry Key" })).toBeInTheDocument();
  });

  it("explains that the password comes from a registered secret", () => {
    render(<Harness />);
    expect(screen.getByText(/one entry of a registered secret/i)).toBeInTheDocument();
  });

  it("shows placeholders only when asked", () => {
    const { unmount } = render(<Harness />);
    expect(screen.getByLabelText(/^name/i)).not.toHaveAttribute("placeholder");
    unmount();

    render(<Harness showPlaceholders />);
    expect(screen.getByLabelText(/^name/i)).toHaveAttribute("placeholder", "e.g. code-review");
  });
});
