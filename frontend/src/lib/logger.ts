import pino from "pino";

const logger = pino({
  browser: { asObject: true },
  level: process.env.NODE_ENV === "production" ? "info" : "debug",
  timestamp: pino.stdTimeFunctions.isoTime,
});

export default logger;
