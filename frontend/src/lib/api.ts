import { HttpAgent } from '@ag-ui/client';
import { A2UIMiddleware, type A2UIInlineCatalogSchema } from '@ag-ui/a2ui-middleware';
import type { Message } from '@ag-ui/core';
import basicCatalogJson from '../generated/basic_catalog.json';
import logger from './logger';

const API_BASE = process.env.BACKEND_BASE_URL ?? 'http://localhost:8000';

export interface SessionInfo {
  session_id: string;
  user_id: string;
  last_update_time: number;
}

export async function listSessions(userId: string): Promise<SessionInfo[]> {
  const response = await fetch(`${API_BASE}/sessions?user_id=${encodeURIComponent(userId)}`);
  if (!response.ok) {
    throw new Error(`List sessions failed: ${response.status}`);
  }
  return response.json() as Promise<SessionInfo[]>;
}

export async function getSessionMessages(sessionId: string, userId: string): Promise<Message[]> {
  const response = await fetch(
    `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/messages?user_id=${encodeURIComponent(userId)}`,
  );
  if (!response.ok) {
    throw new Error(`Get session messages failed: ${response.status}`);
  }
  return response.json() as Promise<Message[]>;
}

export async function createSession(userId: string): Promise<string> {
  const response = await fetch(`${API_BASE}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId }),
  });
  if (!response.ok) {
    throw new Error(`Create session failed: ${response.status}`);
  }
  const data = (await response.json()) as { session_id: string };
  logger.info({ sessionId: data.session_id }, 'session created');
  return data.session_id;
}

export function createChatAgent(sessionId: string): HttpAgent {
  const agent = new HttpAgent({
    url: `${API_BASE}/agent`,
    threadId: sessionId,
  });
  agent.use(new A2UIMiddleware({
    injectA2UITool: true,
    schema: basicCatalogJson as unknown as A2UIInlineCatalogSchema,
  }));
  return agent;
}
