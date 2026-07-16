/** Pino logger instance configured for browser environments with ISO timestamps. */
import pino from "pino";

const logger = pino({
  // `serialize` turns on pino's standard `err` serializer, which unpacks an
  // Error's non-enumerable message/stack. Without it every `logger.error({ err })`
  // reaches the console as an empty `{}` and the failure is unreadable.
  browser: { asObject: true, serialize: true },
  level: process.env.NODE_ENV === "production" ? "info" : "debug",
  timestamp: pino.stdTimeFunctions.isoTime,
});

export default logger;
