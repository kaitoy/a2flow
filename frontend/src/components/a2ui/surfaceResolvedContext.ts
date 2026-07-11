"use client";

import { createContext, useContext } from "react";

/**
 * Whether the enclosing A2UI surface has already been resolved (its `render_a2ui`
 * call already has a tool result) and should render its interactive components as
 * inert. Provided once per surface tree by `A2uiRenderer`; the A2UI schema's
 * `props`/`context` objects have no room for app-level flags like this, so
 * interactive catalog components (Button, TextField, ChoicePicker) read it via
 * context instead — mirrors `@a2ui/react`'s own `MarkdownContext` pattern.
 */
export const SurfaceResolvedContext = createContext(false);

/** Whether the enclosing A2UI surface is resolved and should reject further interaction. */
export function useSurfaceResolved(): boolean {
  return useContext(SurfaceResolvedContext);
}
