import type React from "react";

interface FormFieldProps {
  htmlFor: string;
  label: string;
  required?: boolean;
  error?: string;
  /**
   * Optional control rendered at the right edge of the label row, e.g. an
   * {@link import("./action-icon-button").ActionIconButton} opening a dialog
   * about the field. Keep it label-sized — the row grows to fit it.
   */
  action?: React.ReactNode;
  children: React.ReactNode;
}

/** Labeled form field wrapper with optional required marker, label-row action, and inline error text. */
export function FormField({ htmlFor, label, required, error, action, children }: FormFieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex min-h-5 items-center justify-between gap-2">
        <label htmlFor={htmlFor} className="text-label-caps">
          {label} {required && <span className="text-accent">*</span>}
        </label>
        {action}
      </div>
      {children}
      {error && <p className="text-xs text-error">{error}</p>}
    </div>
  );
}
