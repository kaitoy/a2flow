/** @module NewSessionPage — Renders Chat with no initial session, ready for a new conversation. */
import { Chat } from "@/components/Chat";

export default function NewSessionPage() {
  return <Chat sessionId={null} />;
}
