export const randomUUID = () => globalThis.crypto.randomUUID();
export const randomFillSync = <T extends ArrayBufferView>(buffer: T): T => {
  globalThis.crypto.getRandomValues(buffer as unknown as ArrayBufferView & ArrayBuffer);
  return buffer;
};
export default globalThis.crypto;
