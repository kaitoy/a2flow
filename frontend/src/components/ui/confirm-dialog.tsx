/** @module ConfirmDialog — modal asking the operator to confirm a destructive or irreversible action. */
"use client";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useT } from "@/i18n/provider";

/** Props for {@link ConfirmDialog}. */
interface ConfirmDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Heading naming the action. */
  title: string;
  /** Sentence spelling out what confirming does. */
  description: string;
  /** Called when the operator confirms. */
  onConfirm: () => void;
  /** Called on Cancel, Escape, or a backdrop click. */
  onCancel: () => void;
  /** Label for the confirm button. Defaults to `"Delete"`. */
  confirmLabel?: string;
  /** Style variant for the confirm button. Defaults to `"danger"`. */
  confirmVariant?: "danger" | "primary" | "secondary";
}

/** Modal confirmation dialog with focus trap, keyboard navigation, and backdrop. */
export function ConfirmDialog({
  open,
  title,
  description,
  onConfirm,
  onCancel,
  confirmLabel = "common.delete",
  confirmVariant = "danger",
}: ConfirmDialogProps) {
  const t = useT();
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      panelId="confirm-dialog"
      title={title}
      description={description}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
          <Button variant={confirmVariant} onClick={onConfirm}>
            {t.maybe(confirmLabel)}
          </Button>
        </>
      }
    />
  );
}
