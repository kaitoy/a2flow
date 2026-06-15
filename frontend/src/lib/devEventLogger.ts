/**
 * Log an AG-UI event to the browser console, prefixed with an ISO timestamp.
 * No-op outside of development mode.
 */
export function logAgUiEvent(event: unknown): void {
  if (process.env.NODE_ENV !== "development") return;
  console.log(`[${new Date().toISOString()}] [AG-UI]`, event);
}
