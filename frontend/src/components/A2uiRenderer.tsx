'use client';

import { useEffect, useRef, useState } from 'react';
import { MessageProcessor } from '@a2ui/web_core/v0_9';
import { A2uiSurface, MarkdownContext, type ReactComponentImplementation } from '@a2ui/react/v0_9';
import type { SurfaceModel } from '@a2ui/web_core/v0_9';
import { marked } from 'marked';
import { tailwindCatalog } from './a2uiCatalog';

interface A2uiClientAction {
  name: string;
  context: Record<string, unknown>;
}

const markdownRenderer = (text: string) => Promise.resolve(marked(text) as string);

export function A2uiRenderer({
  payload,
  onAction,
}: {
  payload: unknown;
  onAction?: (message: string) => void;
}) {
  const [surfaces, setSurfaces] = useState<SurfaceModel<ReactComponentImplementation>[]>([]);
  const onActionRef = useRef(onAction);
  onActionRef.current = onAction;

  useEffect(() => {
    const processor = new MessageProcessor<ReactComponentImplementation>([tailwindCatalog]);
    const actionSubs: { unsubscribe: () => void }[] = [];

    const sub = processor.onSurfaceCreated((surface) => {
      const actionSub = surface.onAction.subscribe((action: A2uiClientAction) => {
        const message = JSON.stringify({ action: action.name, ...action.context });
        onActionRef.current?.(message);
      });
      actionSubs.push(actionSub);
      setSurfaces((prev) => [...prev, surface]);
    });

    processor.processMessages(payload as Parameters<typeof processor.processMessages>[0]);
    sub.unsubscribe();

    return () => {
      setSurfaces([]);
      actionSubs.forEach((s) => s.unsubscribe());
    };
  }, []);

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
