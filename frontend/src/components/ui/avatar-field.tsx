/** @module AvatarField — Admin control for uploading or removing a user's avatar. */
"use client";

import { useEffect, useRef, useState } from "react";
import { Avatar, type AvatarUser } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { deleteUserAvatar, type User, uploadUserAvatar } from "@/lib/api";

/** Props for {@link AvatarField}. */
interface AvatarFieldProps {
  /** The user whose avatar is being edited. */
  user: AvatarUser;
  /** Called with the updated user after a successful upload or removal. */
  onChange: (user: User) => void;
}

/** Diameter, in pixels, of the avatar preview shown in the field. */
const PREVIEW_SIZE = 96;

/**
 * Avatar editor for the admin user form: shows the current (or generated)
 * avatar, lets an admin pick an image file to preview and upload, and removes a
 * custom avatar to revert to the generated default.
 */
export function AvatarField({ user, onChange }: AvatarFieldProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Revoke the object URL when the preview changes or the field unmounts.
  useEffect(() => {
    if (!previewUrl) return;
    return () => URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  function handleSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    setError(null);
    setFile(selected);
    setPreviewUrl(selected ? URL.createObjectURL(selected) : null);
  }

  function clearSelection() {
    setFile(null);
    setPreviewUrl(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function handleUpload() {
    if (!file) return;
    setPending(true);
    setError(null);
    try {
      onChange(await uploadUserAvatar(user.id, file));
      clearSelection();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload avatar");
    } finally {
      setPending(false);
    }
  }

  async function handleRemove() {
    setPending(true);
    setError(null);
    try {
      onChange(await deleteUserAvatar(user.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove avatar");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[11px] font-bold uppercase tracking-[0.08em] text-on-surface-variant">
        Avatar
      </span>
      <div className="flex items-center gap-4">
        {previewUrl ? (
          // biome-ignore lint/performance/noImgElement: a local object-URL preview of the chosen file; next/image cannot optimize an in-memory blob.
          <img
            src={previewUrl}
            alt="Avatar preview"
            width={PREVIEW_SIZE}
            height={PREVIEW_SIZE}
            className="shrink-0 rounded-full object-cover"
            style={{ width: PREVIEW_SIZE, height: PREVIEW_SIZE }}
          />
        ) : (
          <Avatar user={user} size={PREVIEW_SIZE} />
        )}
        <div className="flex flex-wrap gap-2">
          <input
            ref={inputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            onChange={handleSelect}
            className="hidden"
          />
          {file ? (
            <>
              <Button type="button" variant="primary" onClick={handleUpload} disabled={pending}>
                {pending ? "Uploading…" : "Upload"}
              </Button>
              <Button type="button" variant="ghost" onClick={clearSelection} disabled={pending}>
                Cancel
              </Button>
            </>
          ) : (
            <>
              <Button
                type="button"
                variant="secondary"
                onClick={() => inputRef.current?.click()}
                disabled={pending}
              >
                Choose image
              </Button>
              {user.avatarUpdatedAt && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={handleRemove}
                  disabled={pending}
                  className="text-error"
                >
                  Remove
                </Button>
              )}
            </>
          )}
        </div>
      </div>
      {error && <p className="text-xs text-error">{error}</p>}
    </div>
  );
}
