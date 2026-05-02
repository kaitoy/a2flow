"use client";

import { type KeyboardEvent, useRef, useState } from "react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";

interface Props {
  onSend: (message: string) => void;
  disabled: boolean;
}

export function ChatInput({ onSend, disabled }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
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
    <div className="border-t border-outline-variant px-4 py-3 bg-surface-container-lowest">
      <div className="flex items-end gap-2 max-w-3xl mx-auto">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          placeholder="Message… (Enter to send, Shift+Enter for newline)"
          disabled={disabled}
          rows={1}
          className="flex-1 resize-none max-h-40 overflow-y-auto"
        />
        <Button
          variant="primary"
          onClick={handleSend}
          disabled={disabled || !value.trim()}
          className="shrink-0"
        >
          Send
        </Button>
      </div>
    </div>
  );
}
