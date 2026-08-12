/**
 * @module AsyncCheckboxPicker — Controlled multi-select whose options are fetched on mount.
 *
 * Extracted from the shape {@link McpToolPicker} established: load on mount,
 * keep the wait and any failure legible instead of rendering an empty list that
 * reads as "there is nothing to pick", and show a filter box once the list gets
 * long. {@link UserPicker} and {@link GroupPicker} are thin wrappers over it, so
 * the two membership editors stay identical without duplicating the markup.
 */
"use client";

import type { LucideIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { Button } from "@/components/ui/button";
import { CheckboxGroup, type CheckboxOption } from "@/components/ui/checkbox-group";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { getApiErrorMessage } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Option count above which a filter box is worth showing. */
export const FILTER_THRESHOLD = 12;

/** One selectable entry: the value stored in the selection and its display label. */
export interface PickerOption {
  value: string;
  label: string;
}

/** What the option fetch is currently doing. */
type LoadState =
  | { phase: "loading" }
  | { phase: "ready"; options: PickerOption[] }
  | { phase: "error"; message: string };

/** Props for {@link AsyncCheckboxPicker}. */
export interface AsyncCheckboxPickerProps {
  /** Field label rendered above the checkbox group. */
  label: string;
  /** Icon shown while the options are loading. */
  icon: LucideIcon;
  /** `name` forwarded to the underlying checkbox inputs. */
  name: string;
  /** Currently selected values. */
  value: string[];
  /** Called with the next selection whenever an option is toggled. */
  onChange: (next: string[]) => void;
  /** Fetches the full option list. Must be stable (wrap in `useCallback`). */
  load: () => Promise<PickerOption[]>;
  /** Message shown when the fetch succeeds but returns nothing. */
  emptyMessage: string;
  /** Sentence shown under the icon while loading. */
  loadingMessage: string;
  /** Sentence shown when the fetch fails, above the raw error and a retry. */
  errorMessage: string;
  /** Placeholder and aria-label of the filter box. */
  filterLabel: string;
  /**
   * Renders the selection as a value instead of a checkbox group, for a viewer
   * who may not write. `onChange` is then never called.
   */
  readOnly?: boolean;
}

/**
 * Multi-select over an asynchronously loaded option list.
 *
 * Already-selected values are always kept in the rendered list, both so the
 * current selection stays visible while filtering and because
 * {@link CheckboxGroup} derives the next selection from the options it was
 * given — dropping a selected option would silently deselect it.
 */
export function AsyncCheckboxPicker({
  label,
  icon,
  name,
  value,
  onChange,
  load,
  emptyMessage,
  loadingMessage,
  errorMessage,
  filterLabel,
  readOnly = false,
}: AsyncCheckboxPickerProps) {
  const [state, setState] = useState<LoadState>({ phase: "loading" });
  const [query, setQuery] = useState("");

  // Guards the post-await state updates. Re-asserted on mount because React
  // StrictMode mounts, unmounts, then remounts in development.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const runLoad = useCallback(async () => {
    setState({ phase: "loading" });
    try {
      const options = await load();
      if (mountedRef.current) setState({ phase: "ready", options });
    } catch (err) {
      if (mountedRef.current) setState({ phase: "error", message: getApiErrorMessage(err) });
    }
  }, [load]);

  useEffect(() => {
    void runLoad();
  }, [runLoad]);

  const allOptions = state.phase === "ready" ? state.options : [];

  const visibleOptions = useMemo<CheckboxOption[]>(() => {
    const needle = query.trim().toLowerCase();
    const matching = needle
      ? allOptions.filter((o) => o.label.toLowerCase().includes(needle) || value.includes(o.value))
      : allOptions;
    return matching.map((o) => ({ value: o.value, label: o.label }));
  }, [allOptions, query, value]);

  if (readOnly) {
    const held = allOptions.filter((o) => value.includes(o.value));
    return (
      <div className="flex flex-col gap-1.5">
        <span className="text-label-caps">{label}</span>
        <ReadOnlyField>
          {held.length === 0 ? EMPTY_VALUE : held.map((o) => o.label).join(", ")}
        </ReadOnlyField>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label-caps">{label}</span>
      {state.phase === "loading" && (
        <div className="rounded-xl glass-panel px-4 py-3">
          <EmptyState icon={icon} compact title="Loading…" description={loadingMessage} />
        </div>
      )}
      {state.phase === "error" && (
        <div className="flex flex-col items-start gap-2 rounded-xl glass-panel px-4 py-3">
          <p className="text-sm text-on-surface-variant">{errorMessage}</p>
          <p className="text-xs text-error">{state.message}</p>
          <Button type="button" variant="secondary" onClick={() => void runLoad()}>
            Retry
          </Button>
        </div>
      )}
      {state.phase === "ready" && (
        <>
          {allOptions.length > FILTER_THRESHOLD && (
            <Input
              aria-label={filterLabel}
              placeholder={`${filterLabel}…`}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          )}
          <CheckboxGroup
            name={name}
            options={visibleOptions}
            value={value}
            onChange={onChange}
            emptyMessage={query.trim() ? "Nothing matches the filter." : emptyMessage}
          />
        </>
      )}
    </div>
  );
}
