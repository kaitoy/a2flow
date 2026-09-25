/**
 * @module code-editor — Test helpers for fields rendered by `CodeEditor`.
 *
 * The editor's content is a contenteditable element, not a form control, so
 * `toHaveValue` and `user.type` do not apply; these go through the CodeMirror
 * view instead.
 */
import { EditorView } from "@codemirror/view";
import { act } from "@testing-library/react";

/**
 * The CodeMirror view owning an editor's content element.
 *
 * @param content - The element found by the field's label.
 * @returns The view.
 */
export function codeEditorView(content: HTMLElement): EditorView {
  const view = EditorView.findFromDOM(content);
  if (!view) throw new Error("element is not inside a CodeEditor");
  return view;
}

/**
 * The editor's current text.
 *
 * @param content - The element found by the field's label.
 * @returns The document text.
 */
export function codeEditorText(content: HTMLElement): string {
  return codeEditorView(content).state.doc.toString();
}

/**
 * Replace the editor's text as if the user had typed it.
 *
 * @param content - The element found by the field's label.
 * @param text - The new document text.
 */
export function setCodeEditorText(content: HTMLElement, text: string): void {
  const view = codeEditorView(content);
  act(() => {
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text } });
  });
}
