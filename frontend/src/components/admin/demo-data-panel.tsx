/**
 * @module DemoDataPanel — Admin Settings section where a tenant's `admin` loads
 * the demo dataset into their tenant or clears it out again.
 */
"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useT } from "@/i18n/provider";
import { clearDemoData, getDemoData, loadDemoData, SUPPRESS_FORBIDDEN_TOAST } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/** Which confirmation, if any, is open. */
type Pending = "load" | "clear" | null;

/**
 * Shows whether the acting tenant holds the demo dataset, with buttons to load
 * it (which also restores anything missing) and to clear it. Both ask for
 * confirmation first. Renders nothing until the status is known, and nothing
 * at all if it cannot be read.
 */
export function DemoDataPanel() {
  const t = useT();
  const dispatch = useAppDispatch();
  const [loaded, setLoaded] = useState<boolean | null>(null);
  const [confirming, setConfirming] = useState<Pending>(null);
  const load = useAsyncAction({ showDone: false });
  const clear = useAsyncAction({ showDone: false });

  useEffect(() => {
    getDemoData(SUPPRESS_FORBIDDEN_TOAST)
      .then((status) => setLoaded(status.loaded))
      .catch(() => setLoaded(null));
  }, []);

  async function onLoad() {
    setConfirming(null);
    try {
      const status = await load.run(loadDemoData);
      setLoaded(status.loaded);
      dispatch(showToast({ message: t("adminSettings.demoData.loadedToast") }));
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function onClear() {
    setConfirming(null);
    try {
      const status = await clear.run(clearDemoData);
      setLoaded(status.loaded);
      const kept = status.keptCount ?? 0;
      dispatch(
        showToast({
          message:
            kept > 0
              ? t("adminSettings.demoData.keptToast", { count: kept })
              : t("adminSettings.demoData.clearedToast"),
        })
      );
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  if (loaded === null) return null;

  const busy = load.inFlight || clear.inFlight;
  return (
    <section className="mt-4 flex flex-col gap-4 rounded-2xl glass-panel-strong p-6">
      <h2 className="font-display text-lg font-semibold tracking-tight text-on-surface">
        {t("adminSettings.demoData.title")}
      </h2>
      <p className="text-sm text-on-surface-variant">{t("adminSettings.demoData.description")}</p>
      <p className="text-sm text-on-surface" data-testid="demo-data-status">
        {loaded ? t("adminSettings.demoData.loaded") : t("adminSettings.demoData.notLoaded")}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="primary"
          disabled={busy}
          status={load.status}
          pendingLabel={t("adminSettings.demoData.loading")}
          onClick={() => setConfirming("load")}
          data-testid="demo-data-load"
        >
          {t("adminSettings.demoData.load")}
        </Button>
        <Button
          variant="danger"
          disabled={busy || !loaded}
          status={clear.status}
          pendingLabel={t("adminSettings.demoData.clearing")}
          onClick={() => setConfirming("clear")}
          data-testid="demo-data-clear"
        >
          {t("adminSettings.demoData.clear")}
        </Button>
      </div>

      <ConfirmDialog
        open={confirming === "load"}
        title={t("adminSettings.demoData.loadConfirmTitle")}
        description={t("adminSettings.demoData.loadConfirmDescription")}
        confirmLabel="adminSettings.demoData.load"
        confirmVariant="primary"
        onConfirm={onLoad}
        onCancel={() => setConfirming(null)}
      />
      <ConfirmDialog
        open={confirming === "clear"}
        title={t("adminSettings.demoData.clearConfirmTitle")}
        description={t("adminSettings.demoData.clearConfirmDescription")}
        confirmLabel="adminSettings.demoData.clear"
        onConfirm={onClear}
        onCancel={() => setConfirming(null)}
      />
    </section>
  );
}
