"use client";

import { animated, useSpring } from "@react-spring/web";
import { type KeyboardEvent, useRef, useState } from "react";
import { useMotionConfig } from "@/lib/motion";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";

interface Props {
  onSend: (message: string) => void;
  disabled: boolean;
}

/** Auto-resizing textarea input that sends on Enter and inserts a newline on Shift+Enter. */
export function ChatInput({ onSend, disabled }: Props) {
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
    if (e.key === "Enter" && !e.shiftKey) {
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
    <div className="shrink-0 px-4 pb-6 pt-2">
      <animated.div
        style={{
          boxShadow: glow.glow.to(
            (g) =>
              `var(--shadow-glass-lg), 0 0 ${36 + g * 32}px rgba(var(--color-accent-rgb), ${0.0 + g * 0.55})`
          ),
        }}
        className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl glass-panel-strong p-2"
      >
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          placeholder="Message…  (Enter to send · Shift+Enter for newline)"
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
