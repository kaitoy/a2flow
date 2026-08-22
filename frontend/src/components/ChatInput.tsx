"use client";

import { animated, useSpring } from "@react-spring/web";
import { type KeyboardEvent, type ReactNode, useRef, useState } from "react";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useMotionConfig } from "@/lib/motion";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";

interface Props {
  onSend: (message: string) => void;
  disabled: boolean;
  /**
   * Optional control rendered before the textarea (e.g. a menu of extra
   * chat actions). Carries its own alignment classes, matching how the Send
   * button aligns itself to the bottom of a multi-line textarea.
   */
  leading?: ReactNode;
}

/**
 * Auto-resizing textarea input that sends on Ctrl+Enter (or Cmd+Enter on
 * Mac) and inserts a newline on Enter or Shift+Enter. On coarse-pointer
 * (touch) devices no key combination sends — soft keyboards have no
 * reliable modifier keys, so sending happens through the Send button.
 */
export function ChatInput({ onSend, disabled, leading }: Props) {
  const coarsePointer = useMediaQuery("(pointer: coarse)");
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const config = useMotionConfig("snappy");
  const [glow, glowApi] = useSpring(() => ({
    glow: 0,
    config,
  }));

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
    glowApi.start({
      from: { glow: 1 },
      to: { glow: 0 },
      reset: true,
    });
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !coarsePointer) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  };

  return (
    <div className="shrink-0 px-4 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-2">
      <animated.div
        style={{
          boxShadow: glow.glow.to(
            (g) =>
              `var(--shadow-glass-lg), 0 0 ${36 + g * 32}px rgba(var(--color-accent-rgb), ${0.0 + g * 0.55})`
          ),
        }}
        className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl glass-panel-strong p-2"
      >
        {leading}
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          placeholder={
            coarsePointer ? "Message…" : "Message…  (Ctrl/⌘+Enter to send · Enter for newline)"
          }
          disabled={disabled}
          rows={1}
          className="flex-1 resize-none max-h-40 overflow-y-auto !border-transparent !bg-transparent !shadow-none focus:!ring-0"
        />
        <Button
          variant="primary"
          onClick={handleSend}
          disabled={disabled || !value.trim()}
          className="shrink-0 self-end"
        >
          Send
        </Button>
      </animated.div>
    </div>
  );
}
