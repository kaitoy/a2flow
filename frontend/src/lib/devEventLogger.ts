export function logAgUiEvent(event: unknown): void {
  if (process.env.NODE_ENV !== "development") return;
  console.log("[AG-UI]", event);
}
