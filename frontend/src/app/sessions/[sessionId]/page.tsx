import { Chat } from '@/components/Chat';

export default async function SessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return <Chat key={sessionId} sessionId={sessionId} />;
}
