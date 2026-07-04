/** @module AvatarField — Admin control for uploading or removing a user's avatar. */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Avatar, type AvatarUser } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { useAsyncAction } from "@/hooks/useAsyncAction";
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
  const [error, setError] = useState<string | null>(null);

  // Upload gets the full three-stage feedback (incl. the "done" wiggle); remove
  // skips the done stage because its button unmounts as soon as the avatar is
  // gone, so there is nothing left to celebrate on.
  const upload = useAsyncAction();
  const remove = useAsyncAction({ showDone: false });
  // Defer clearing the picked file until the upload's "done" wiggle has finished
  // (see the effect below): clearing immediately would unmount the Upload button
  // before its celebratory wiggle could play.
  const uploadedRef = useRef(false);

  // Revoke the object URL when the preview changes or the field unmounts.
  useEffect(() => {
    if (!previewUrl) return;
    return () => URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const clearSelection = useCallback(() => {
    setFile(null);
    setPreviewUrl(null);
    if (inputRef.current) inputRef.current.value = "";
  }, []);

  // Once the upload's "done" stage has elapsed and the button reverts to idle,
  // collapse the preview/Upload UI back to the Choose-image/Remove view.
  useEffect(() => {
    if (uploadedRef.current && upload.status === "idle") {
      uploadedRef.current = false;
      clearSelection();
    }
  }, [upload.status, clearSelection]);

  function handleSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    setError(null);
    setFile(selected);
    setPreviewUrl(selected ? URL.createObjectURL(selected) : null);
  }

  async function handleUpload() {
    if (!file) return;
    setError(null);
    try {
      await upload.run(async () => {
        onChange(await uploadUserAvatar(user.id, file));
      });
      // Selection is cleared by the effect above once the wiggle has played.
      uploadedRef.current = true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload avatar");
    }
  }

  async function handleRemove() {
    setError(null);
    try {
      await remove.run(async () => {
        onChange(await deleteUserAvatar(user.id));
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove avatar");
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label-caps">Avatar</span>
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
              <Button
                type="button"
                variant="primary"
                onClick={handleUpload}
                disabled={upload.inFlight}
                status={upload.status}
                pendingLabel="Uploading…"
                doneLabel="Uploaded!"
              >
                Upload
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={clearSelection}
                disabled={upload.inFlight || upload.status !== "idle"}
              >
                Cancel
              </Button>
            </>
          ) : (
            <>
              <Button
                type="button"
                variant="secondary"
                onClick={() => inputRef.current?.click()}
                disabled={remove.inFlight}
              >
                Choose image
              </Button>
              {user.avatarUpdatedAt && (
                <Button
                  type="button"
                  variant="danger"
                  onClick={handleRemove}
                  disabled={remove.inFlight}
                  status={remove.status}
                  pendingLabel="Removing…"
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
