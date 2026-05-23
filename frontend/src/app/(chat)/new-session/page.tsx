/** @module NewSessionPage — Renders an empty chat panel ready for a new conversation. */
import { Chat } from "@/components/Chat";

export default function NewSessionPage() {
  return <Chat sessionId={null} />;
}
