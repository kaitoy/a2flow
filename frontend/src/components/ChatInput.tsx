"use client";

import { animated, useSpring } from "@react-spring/web";
import { Paperclip } from "lucide-react";
import { type DragEvent, type KeyboardEvent, type ReactNode, useRef, useState } from "react";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useMotionConfig } from "@/lib/motion";
import { formatFileSize, MAX_ATTACHMENT_BYTES } from "@/lib/sessionFileTool";
import { Button } from "./ui/button";
import { Chip } from "./ui/chip";
import { Textarea } from "./ui/textarea";

/**
 * One file staged in the composer, waiting to be sent.
 *
 * The id exists only to key its chip: two files can share a name, and staging
 * order changes as chips are removed, so neither the name nor the index
 * identifies a chip stably enough for React to keep it in place.
 */
interface StagedFile {
  id: string;
  file: File;
}

interface Props {
  /**
   * Called with the typed message and the files attached alongside it. `files`
   * is empty unless {@link Props.allowAttachments} is set.
   */
  onSend: (message: string, files: File[]) => void;
  disabled: boolean;
  /**
   * Optional control rendered before the textarea (e.g. a menu of extra
   * chat actions). Carries its own alignment classes, matching how the Send
   * button aligns itself to the bottom of a multi-line textarea.
   */
  leading?: ReactNode;
  /**
   * Enables attaching files: a paperclip button, a row of removable chips for
   * what is staged, and drop-to-attach over the whole composer. Off by default,
   * because only a workflow session has a file store to attach to.
   */
  allowAttachments?: boolean;
}

/**
 * Auto-resizing textarea input that sends on Ctrl+Enter (or Cmd+Enter on
 * Mac) and inserts a newline on Enter or Shift+Enter. On coarse-pointer
 * (touch) devices no key combination sends — soft keyboards have no
 * reliable modifier keys, so sending happens through the Send button.
 *
 * With {@link Props.allowAttachments}, files staged here are held as plain
 * `File` objects and handed to {@link Props.onSend} only when the message is
 * sent. Nothing is uploaded before that, which is what makes removing a chip a
 * purely local act: an abandoned draft leaves nothing behind on the server.
 */
export function ChatInput({ onSend, disabled, leading, allowAttachments = false }: Props) {
  const coarsePointer = useMediaQuery("(pointer: coarse)");
  const [value, setValue] = useState("");
  const [files, setFiles] = useState<StagedFile[]>([]);
  const [rejected, setRejected] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const config = useMotionConfig("snappy");
  const [glow, glowApi] = useSpring(() => ({
    glow: 0,
    config,
  }));

  const canSend = !disabled && (value.trim().length > 0 || files.length > 0);

  /**
   * Stage the files that pass the size check, reporting the ones that do not.
   *
   * The limit is checked here only to spare the user a doomed round trip; the
   * server enforces its own and stays authoritative.
   */
  const addFiles = (picked: File[]) => {
    const tooLarge = picked.filter((f) => f.size > MAX_ATTACHMENT_BYTES);
    const accepted = picked.filter((f) => f.size <= MAX_ATTACHMENT_BYTES);
    setRejected(
      tooLarge.length === 0
        ? null
        : `${tooLarge.map((f) => f.name).join(", ")} — over the ${formatFileSize(
            MAX_ATTACHMENT_BYTES
          )} limit`
    );
    if (accepted.length > 0) {
      setFiles((current) => [
        ...current,
        ...accepted.map((file) => ({ id: crypto.randomUUID(), file })),
      ]);
    }
  };

  const handleSend = () => {
    if (!canSend) return;
    onSend(
      value.trim(),
      files.map((staged) => staged.file)
    );
    setValue("");
    setFiles([]);
    setRejected(null);
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

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    if (!allowAttachments) return;
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    addFiles(Array.from(e.dataTransfer.files));
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    if (!allowAttachments || disabled) return;
    e.preventDefault();
    setDragging(true);
  };

  return (
    <div className="shrink-0 px-4 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-2">
      {/* Drop-to-attach hangs off the whole composer; the paperclip button is
          the keyboard-reachable path to the same thing. */}
      <animated.div
        style={{
          boxShadow: glow.glow.to(
            (g) =>
              `var(--shadow-glass-lg), 0 0 ${36 + g * 32}px rgba(var(--color-accent-rgb), ${0.0 + g * 0.55})`
          ),
        }}
        onDragOver={handleDragOver}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={[
          "mx-auto flex max-w-3xl flex-col gap-2 rounded-2xl glass-panel-strong p-2",
          dragging ? "ring-2 ring-accent/50" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {files.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-1 pt-1">
            {files.map(({ id, file }) => (
              <Chip
                key={id}
                label={file.name}
                description={formatFileSize(file.size)}
                onRemove={() => setFiles((current) => current.filter((s) => s.id !== id))}
              />
            ))}
          </div>
        )}
        {rejected && (
          <p className="px-1 text-xs text-error" role="alert">
            {rejected}
          </p>
        )}
        <div className="flex items-end gap-2">
          {leading}
          {allowAttachments && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                hidden
                onChange={(e) => {
                  addFiles(Array.from(e.target.files ?? []));
                  // Clear the input so picking the same file twice re-fires change.
                  e.target.value = "";
                }}
              />
              <button
                type="button"
                aria-label="Attach files"
                disabled={disabled}
                onClick={() => fileInputRef.current?.click()}
                className="inline-flex size-9 shrink-0 cursor-pointer items-center justify-center self-end rounded-full text-on-surface-variant transition-colors duration-[var(--motion-duration-fast)] ease-[var(--motion-ease-standard)] hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Paperclip size={18} strokeWidth={1.8} aria-hidden />
              </button>
            </>
          )}
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
            disabled={!canSend}
            className="shrink-0 self-end"
          >
            Send
          </Button>
        </div>
      </animated.div>
    </div>
  );
}
