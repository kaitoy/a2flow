"use client";

import { renderMarkdown } from "@a2ui/markdown-it";
import { A2uiSurface, MarkdownContext, type ReactComponentImplementation } from "@a2ui/react/v0_9";
import type { SurfaceModel } from "@a2ui/web_core/v0_9";
import { MessageProcessor } from "@a2ui/web_core/v0_9";
import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";
import { useEffect, useRef, useState } from "react";
import logger from "@/lib/logger";
import { SurfaceResolvedContext } from "./a2ui/surfaceResolvedContext";
import { tailwindCatalog } from "./a2uiCatalog";

/**
 * Process a raw A2UI payload and render the resulting surfaces using the tailwind catalog.
 * Surfaces are re-processed from scratch whenever the payload reference changes.
 * Nullish payloads (e.g. middleware lifecycle snapshots without operations) render nothing.
 *
 * A payload `MessageProcessor` rejects (invalid A2UI from the agent) renders nothing
 * and is logged, rather than throwing and taking the surrounding message history
 * down with it — the payload is LLM output, so it can be malformed at any time.
 *
 * The payload is deep-cloned before processing: it comes out of the Redux
 * store, which freezes state objects, while `MessageProcessor` adopts the
 * payload's data model by reference and mutates it when the user edits input
 * components (TextField, ChoicePicker). Without the clone every edit throws
 * "Cannot assign to read only property" and the surface never captures input.
 *
 * `resolved` marks a surface whose `render_a2ui` call already has an answer (e.g.
 * after a page reload, or immediately after the user acts on it): interactive
 * catalog components read it via {@link SurfaceResolvedContext} and render inert,
 * so an already-answered surface can never be resubmitted.
 *
 * `onAction` receives the surface's entire data model alongside the action. The
 * action's own `context` carries only the bindings the agent declared on the
 * acted-on component, so it is neither a complete nor a path-faithful record of
 * what the user entered; the data model is both, and is what the agent reads and
 * what a resumed session is redisplayed from.
 *
 * Text components render Markdown via `@a2ui/markdown-it`'s `renderMarkdown`
 * (supplied through {@link MarkdownContext}), which sanitizes with DOMPurify —
 * A2UI payloads originate from the agent and must be treated as untrusted HTML.
 */
export function A2uiRenderer({
  payload,
  onAction,
  resolved = false,
}: {
  payload: unknown;
  onAction?: (action: A2UIUserAction, values: Record<string, unknown>) => void;
  resolved?: boolean;
}) {
  const [surfaces, setSurfaces] = useState<SurfaceModel<ReactComponentImplementation>[]>([]);
  const onActionRef = useRef(onAction);
  onActionRef.current = onAction;

  useEffect(() => {
    if (payload == null) return;
    const processor = new MessageProcessor<ReactComponentImplementation>([tailwindCatalog]);
    const actionSubs: { unsubscribe: () => void }[] = [];
    const created: SurfaceModel<ReactComponentImplementation>[] = [];

    const sub = processor.onSurfaceCreated((surface) => {
      const actionSub = surface.onAction.subscribe((action: A2UIUserAction) => {
        // `get("/")` returns the data model root — every value the input
        // components wrote, under the same paths they bind to.
        const root: unknown = surface.dataModel.get("/");
        const values =
          root !== null && typeof root === "object" && !Array.isArray(root)
            ? (root as Record<string, unknown>)
            : {};
        onActionRef.current?.(
          {
            name: action.name,
            surfaceId: surface.id,
            sourceComponentId: action.sourceComponentId,
            context: action.context,
            timestamp: new Date().toISOString(),
          },
          values
        );
      });
      actionSubs.push(actionSub);
      created.push(surface);
    });

    // The payload is an LLM's tool-call arguments, so it can be invalid A2UI (an
    // unknown component, a component missing its type). MessageProcessor throws
    // on those, and an uncaught throw here takes down the whole session view —
    // the surrounding history included. Commit the surfaces only once the whole
    // payload processed, so a throw drops the unrenderable surface rather than
    // leaving behind the half-built one `createSurface` had already created.
    try {
      processor.processMessages(
        structuredClone(payload) as Parameters<typeof processor.processMessages>[0]
      );
      setSurfaces(created);
    } catch (err) {
      logger.error({ err }, "failed to process A2UI payload");
    }
    sub.unsubscribe();

    return () => {
      setSurfaces([]);
      actionSubs.forEach((s) => {
        s.unsubscribe();
      });
    };
  }, [payload]);

  if (surfaces.length === 0) return null;

  return (
    <MarkdownContext.Provider value={renderMarkdown}>
      <SurfaceResolvedContext.Provider value={resolved}>
        <div className="mt-1 space-y-2">
          {surfaces.map((surface) => (
            <A2uiSurface key={surface.id} surface={surface} />
          ))}
        </div>
      </SurfaceResolvedContext.Provider>
    </MarkdownContext.Provider>
  );
}
