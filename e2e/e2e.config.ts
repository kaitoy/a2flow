import { web } from "@e2e-dev/web";
import type { E2EConfig } from "e2e";

/**
 * The e2e suite's configuration: one Chromium target against the app that
 * `start.sh` serves on 127.0.0.1:3099. No `agents` block, because no test uses
 * agent steps, so the suite needs no model. The backend's own LLM is the
 * scripted one in backend/scripts/e2e_server.py. The locale is pinned so the
 * GUI renders in English whatever the host's language is.
 */
export default {
  targets: [
    {
      engine: web({ locale: "en-US" }),
      app: {
        url: "http://127.0.0.1:3099",
        command: {
          executable: "bash",
          args: ["start.sh"],
          startupTimeout: 180_000,
          reuseExisting: true,
          log: ".e2e/logs/app.log",
        },
      },
    },
  ],
  reporters: ["list", "junit"],
} satisfies E2EConfig;
