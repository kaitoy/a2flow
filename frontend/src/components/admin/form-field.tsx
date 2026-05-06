import type React from "react";

interface FormFieldProps {
  htmlFor: string;
  label: string;
  required?: boolean;
  error?: string;
  children: React.ReactNode;
}

export function FormField({ htmlFor, label, required, error, children }: FormFieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor={htmlFor}
        className="text-xs font-bold uppercase tracking-[0.04em] text-on-surface-variant"
      >
        {label} {required && <span className="text-error">*</span>}
      </label>
      {children}
      {error && <p className="text-xs text-error">{error}</p>}
    </div>
  );
}
