/** @module SessionPage — Renders Chat for an existing session identified by the URL param. */
import { Chat } from "@/components/Chat";

export default async function SessionPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  return <Chat key={sessionId} sessionId={sessionId} />;
}
