"use client";

import { renderMarkdown } from "@a2ui/markdown-it";
import { A2uiSurface, MarkdownContext, type ReactComponentImplementation } from "@a2ui/react/v0_9";
import type { SurfaceModel } from "@a2ui/web_core/v0_9";
import { MessageProcessor } from "@a2ui/web_core/v0_9";
import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";
import { useEffect, useRef, useState } from "react";
import { SurfaceResolvedContext } from "./a2ui/surfaceResolvedContext";
import { tailwindCatalog } from "./a2uiCatalog";

/**
 * Process a raw A2UI payload and render the resulting surfaces using the tailwind catalog.
 * Surfaces are re-processed from scratch whenever the payload reference changes.
 * Nullish payloads (e.g. middleware lifecycle snapshots without operations) render nothing.
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
  onAction?: (action: A2UIUserAction) => void;
  resolved?: boolean;
}) {
  const [surfaces, setSurfaces] = useState<SurfaceModel<ReactComponentImplementation>[]>([]);
  const onActionRef = useRef(onAction);
  onActionRef.current = onAction;

  useEffect(() => {
    if (payload == null) return;
    const processor = new MessageProcessor<ReactComponentImplementation>([tailwindCatalog]);
    const actionSubs: { unsubscribe: () => void }[] = [];

    const sub = processor.onSurfaceCreated((surface) => {
      const actionSub = surface.onAction.subscribe((action: A2UIUserAction) => {
        onActionRef.current?.({
          name: action.name,
          surfaceId: surface.id,
          sourceComponentId: action.sourceComponentId,
          context: action.context,
          timestamp: new Date().toISOString(),
        });
      });
      actionSubs.push(actionSub);
      setSurfaces((prev) => [...prev, surface]);
    });

    processor.processMessages(
      structuredClone(payload) as Parameters<typeof processor.processMessages>[0]
    );
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
