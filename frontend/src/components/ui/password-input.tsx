/** @module PasswordInput — masked text input with a show/hide toggle button. */
"use client";

import { Eye, EyeOff } from "lucide-react";
import type React from "react";
import { useState } from "react";
import { Input } from "@/components/ui/input";

/** Props for {@link PasswordInput}; every native input attribute except `type`. */
export interface PasswordInputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {}

/**
 * Password/secret input masked by default, with a trailing toggle button that
 * reveals the current value as plain text while active.
 */
export function PasswordInput({ className, ...rest }: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  const Icon = visible ? EyeOff : Eye;
  const cls = className ? `pr-10 ${className}` : "pr-10";

  return (
    <div className="relative w-full">
      <Input type={visible ? "text" : "password"} className={cls} {...rest} />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Hide value" : "Show value"}
        className="absolute inset-y-0 right-0 flex items-center px-3 text-on-surface-variant transition-colors hover:text-accent"
      >
        <Icon size={16} strokeWidth={1.8} aria-hidden />
      </button>
    </div>
  );
}
