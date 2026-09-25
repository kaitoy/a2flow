import { forceLinting } from "@codemirror/lint";
import { EditorView } from "@codemirror/view";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CodeEditor } from "./code-editor";

/** The CodeMirror view behind the editor labelled "Source". */
function viewOf(): EditorView {
  const view = EditorView.findFromDOM(screen.getByLabelText("Source"));
  if (!view) throw new Error("no editor view");
  return view;
}

function renderEditor(props: Partial<React.ComponentProps<typeof CodeEditor>> = {}) {
  return render(
    <>
      <span id="source-label">Source</span>
      <CodeEditor id="source" labelledBy="source-label" value="" language="python" {...props} />
    </>
  );
}

describe("CodeEditor", () => {
  it("renders the value in a textbox labelled by the given element", () => {
    renderEditor({ value: "def f(): pass" });
    const content = screen.getByLabelText("Source");
    expect(content).toHaveAttribute("role", "textbox");
    expect(content).toHaveAttribute("id", "source");
    expect(content).toHaveTextContent("def f(): pass");
  });

  it("highlights keywords", () => {
    renderEditor({ value: "def f(): pass" });
    const keyword = screen.getByText("def");
    expect(keyword.tagName).toBe("SPAN");
    expect(keyword.className).not.toBe("");
  });

  it("reports edits through onChange", () => {
    const onChange = vi.fn();
    renderEditor({ value: "x", onChange });
    viewOf().dispatch({ changes: { from: 1, insert: "y" } });
    expect(onChange).toHaveBeenLastCalledWith("xy");
  });

  it("replaces the document when the value changes from outside", () => {
    const { rerender } = renderEditor({ value: "old" });
    rerender(
      <>
        <span id="source-label">Source</span>
        <CodeEditor id="source" labelledBy="source-label" value="new" language="python" />
      </>
    );
    expect(viewOf().state.doc.toString()).toBe("new");
  });

  it("is not editable when read-only", () => {
    renderEditor({ value: "x", readOnly: true });
    expect(screen.getByLabelText("Source")).toHaveAttribute("contenteditable", "false");
    expect(viewOf().state.readOnly).toBe(true);
  });

  it("marks the content invalid", () => {
    renderEditor({ invalid: true });
    expect(screen.getByLabelText("Source")).toHaveAttribute("aria-invalid", "true");
  });

  it("underlines what the lint source reports", async () => {
    const lint = vi.fn(() => [
      { from: 0, to: 3, severity: "error" as const, message: "bad start" },
    ]);
    const { container } = renderEditor({ value: "def (", lint });
    forceLinting(viewOf());
    await waitFor(() => expect(container.querySelector(".cm-lintRange-error")).not.toBeNull());
    expect(lint).toHaveBeenCalled();
  });

  it("does not lint a read-only view", async () => {
    const lint = vi.fn(() => []);
    renderEditor({ value: "x", lint, readOnly: true });
    forceLinting(viewOf());
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(lint).not.toHaveBeenCalled();
  });
});
