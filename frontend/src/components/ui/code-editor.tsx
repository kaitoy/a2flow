/**
 * @module CodeEditor — Syntax-highlighted source editor with inline lint marks.
 *
 * A thin React wrapper over CodeMirror 6. Colors come from the `--c-code-*`
 * tokens in `globals.css`, so the editor follows the light/dark theme through
 * CSS variables alone. Lint results are drawn as wavy underlines (red for an
 * error, amber for a warning) with the message on hover and a gutter marker.
 */
"use client";

import { indentWithTab } from "@codemirror/commands";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { type Diagnostic, linter, lintGutter } from "@codemirror/lint";
import { Compartment, EditorState, type Extension } from "@codemirror/state";
import { EditorView, keymap, tooltips } from "@codemirror/view";
import { tags as t } from "@lezer/highlight";
import { basicSetup } from "codemirror";
import { useEffect, useRef } from "react";

/** A language the editor can highlight. */
export type CodeLanguage = "python" | "javascript";

/** Computes the lint marks for the editor's current document. */
export type CodeLintSource = (view: EditorView) => Diagnostic[] | Promise<Diagnostic[]>;

/** Props for {@link CodeEditor}. */
export interface CodeEditorProps {
  /** `id` of the editable content element, matching the field label's `htmlFor`. */
  id: string;
  /** `id` of the element labelling the editor (a `<label for>` cannot target it). */
  labelledBy: string;
  /** The source text. A change from outside (e.g. a form reset) replaces the document. */
  value: string;
  /** Called with the full text after every edit. */
  onChange?: (value: string) => void;
  /** Language to highlight. */
  language: CodeLanguage;
  /** Lint source; keep its identity stable, since a new one restarts linting. */
  lint?: CodeLintSource;
  /** Renders a non-editable, highlighted view with no editor chrome. */
  readOnly?: boolean;
  /** Marks the content `aria-invalid`, e.g. while the field has a form error. */
  invalid?: boolean;
}

/** Maps highlight tags to the `--c-code-*` tokens. */
const highlightStyle = HighlightStyle.define([
  { tag: t.keyword, color: "var(--c-code-keyword)" },
  { tag: [t.string, t.regexp], color: "var(--c-code-string)" },
  { tag: t.number, color: "var(--c-code-number)" },
  { tag: [t.bool, t.null, t.atom, t.self], color: "var(--c-code-constant)" },
  { tag: t.comment, color: "var(--c-code-comment)", fontStyle: "italic" },
  {
    tag: [t.function(t.variableName), t.function(t.propertyName)],
    color: "var(--c-code-function)",
  },
  { tag: [t.typeName, t.className], color: "var(--c-code-type)" },
]);

/** Wavy underline in `color`; replaces CodeMirror's fixed-color SVG squiggle. */
function squiggle(color: string) {
  return {
    backgroundImage: "none",
    textDecoration: `underline wavy ${color}`,
    textDecorationSkipInk: "none",
    textUnderlineOffset: "3px",
  };
}

/** Editor surface: transparent over its container, tokens for every color. */
const editorTheme = EditorView.theme({
  "&": { color: "var(--c-on-surface)", backgroundColor: "transparent", maxHeight: "40rem" },
  "&.cm-focused": { outline: "none" },
  ".cm-scroller": {
    fontFamily: "var(--font-mono)",
    fontSize: "0.8125rem",
    fontWeight: "400",
    lineHeight: "1.6",
  },
  ".cm-content": { caretColor: "var(--c-accent)" },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--c-accent)" },
  ".cm-gutters": {
    backgroundColor: "transparent",
    color: "var(--c-on-surface-variant)",
    border: "none",
  },
  ".cm-activeLine, .cm-activeLineGutter": {
    backgroundColor: "color-mix(in oklch, var(--c-accent) 6%, transparent)",
  },
  "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground":
    { backgroundColor: "var(--c-accent-soft)" },
  ".cm-matchingBracket, &.cm-focused .cm-matchingBracket": {
    backgroundColor: "var(--c-accent-soft)",
    outline: "none",
  },
  ".cm-lintRange-error": squiggle("var(--c-error)"),
  ".cm-lintRange-warning": squiggle("var(--c-code-warning)"),
  ".cm-lintRange-info": squiggle("var(--c-accent)"),
  ".cm-tooltip": {
    backgroundColor: "var(--c-glass-strong)",
    backdropFilter: "blur(12px)",
    border: "1px solid var(--c-outline)",
    borderRadius: "0.5rem",
    color: "var(--c-on-surface)",
    overflow: "hidden",
  },
  ".cm-tooltip-autocomplete ul li[aria-selected]": {
    backgroundColor: "var(--c-accent-soft)",
    color: "var(--c-on-surface)",
  },
  ".cm-diagnostic": { fontSize: "0.75rem" },
  ".cm-diagnostic-error": { borderLeftColor: "var(--c-error)" },
  ".cm-diagnostic-warning": { borderLeftColor: "var(--c-code-warning)" },
  ".cm-diagnostic-info": { borderLeftColor: "var(--c-accent)" },
});

/** Room for about sixteen lines while editing, the old textarea's height. */
const editableHeight = EditorView.theme({ ".cm-content, .cm-gutter": { minHeight: "24rem" } });

const languageSlot = new Compartment();
const lintSlot = new Compartment();
const modeSlot = new Compartment();
const ariaSlot = new Compartment();

/** The per-prop extensions, each loaded into its own compartment. */
function slots({
  id,
  labelledBy,
  language,
  lint,
  readOnly,
  invalid,
}: CodeEditorProps): [Compartment, Extension][] {
  return [
    [languageSlot, language === "python" ? python() : javascript()],
    [lintSlot, lint && !readOnly ? [linter(lint, { delay: 500 }), lintGutter()] : []],
    [
      modeSlot,
      readOnly ? [EditorState.readOnly.of(true), EditorView.editable.of(false)] : editableHeight,
    ],
    [
      ariaSlot,
      EditorView.contentAttributes.of({
        id,
        "aria-labelledby": labelledBy,
        "aria-invalid": String(Boolean(invalid)),
      }),
    ],
  ];
}

/**
 * Syntax-highlighted code editor bound to a string value.
 *
 * Tab indents; Escape then Tab moves focus on, per CodeMirror's keyboard
 * convention. While `readOnly`, the same highlighting renders without the
 * editor's own surface, for a caller to place on a read-only one.
 *
 * @param props - The value, its language, and optional lint and modes.
 * @returns The editor.
 */
export function CodeEditor(props: CodeEditorProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(props.onChange);

  useEffect(() => {
    onChangeRef.current = props.onChange;
  }, [props.onChange]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: the view is built once; later prop changes flow in through the effects below
  useEffect(() => {
    const view = new EditorView({
      parent: hostRef.current as HTMLDivElement,
      state: EditorState.create({
        doc: props.value,
        extensions: [
          basicSetup,
          keymap.of([indentWithTab]),
          syntaxHighlighting(highlightStyle),
          editorTheme,
          // The rounded surface clips its overflow, which would cut off lint
          // and autocomplete tooltips; CodeMirror carries the theme classes over.
          tooltips({ parent: document.body }),
          ...slots(props).map(([slot, extension]) => slot.of(extension)),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) onChangeRef.current?.(update.state.doc.toString());
          }),
        ],
      }),
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, []);

  useEffect(() => {
    const view = viewRef.current;
    if (view && view.state.doc.toString() !== props.value) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: props.value } });
    }
  }, [props.value]);

  const { id, labelledBy, language, lint, readOnly, invalid } = props;
  useEffect(() => {
    viewRef.current?.dispatch({
      effects: slots({ id, labelledBy, language, lint, readOnly, invalid, value: "" }).map(
        ([slot, extension]) => slot.reconfigure(extension)
      ),
    });
  }, [id, labelledBy, language, lint, readOnly, invalid]);

  return (
    <div
      ref={hostRef}
      className={
        readOnly
          ? undefined
          : "overflow-hidden rounded-xl glass-panel transition-all duration-150 focus-within:ring-2 focus-within:ring-accent/50"
      }
    />
  );
}
