export const randomUUID = () => globalThis.crypto.randomUUID();
export const randomFillSync = <T extends ArrayBufferView>(buffer: T): T => {
  globalThis.crypto.getRandomValues(buffer as unknown as ArrayBufferView<ArrayBuffer>);
  return buffer;
};
export default globalThis.crypto;

/**
 * Stub for `node:crypto`'s `createHash`, which `@ag-ui/a2ui-middleware` imports
 * to derive message ids in `processUserAction`. That path only runs for a
 * forwarded `a2uiAction.userAction`, which this app never sends, so the stub
 * fails loudly instead of shipping a hash implementation to the browser.
 */
// ponytail: throwing stub; implement SHA-256 here if the app starts forwarding userAction.
export const createHash = (algorithm: string): never => {
  throw new Error(`crypto.createHash("${algorithm}") is not available in the browser`);
};
