import type React from "react";

interface FormFieldProps {
  htmlFor: string;
  label: string;
  required?: boolean;
  error?: string;
  children: React.ReactNode;
}

/** Labeled form field wrapper with optional required marker and inline error text. */
export function FormField({ htmlFor, label, required, error, children }: FormFieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={htmlFor}
        className="text-[11px] font-bold uppercase tracking-[0.08em] text-on-surface-variant"
      >
        {label} {required && <span className="text-accent">*</span>}
      </label>
      {children}
      {error && <p className="text-xs text-error">{error}</p>}
    </div>
  );
}
