"use client";

import { A2uiSurface, MarkdownContext, type ReactComponentImplementation } from "@a2ui/react/v0_9";
import type { SurfaceModel } from "@a2ui/web_core/v0_9";
import { MessageProcessor } from "@a2ui/web_core/v0_9";
import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";
import { marked } from "marked";
import { useEffect, useRef, useState } from "react";
import { tailwindCatalog } from "./a2uiCatalog";

const markdownRenderer = (text: string) => Promise.resolve(marked(text) as string);

export function A2uiRenderer({
  payload,
  onAction,
}: {
  payload: unknown;
  onAction?: (action: A2UIUserAction) => void;
}) {
  const [surfaces, setSurfaces] = useState<SurfaceModel<ReactComponentImplementation>[]>([]);
  const onActionRef = useRef(onAction);
  onActionRef.current = onAction;

  useEffect(() => {
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

    processor.processMessages(payload as Parameters<typeof processor.processMessages>[0]);
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
    <MarkdownContext.Provider value={markdownRenderer}>
      <div className="mt-1 space-y-2">
        {surfaces.map((surface) => (
          <A2uiSurface key={surface.id} surface={surface} />
        ))}
      </div>
    </MarkdownContext.Provider>
  );
}
