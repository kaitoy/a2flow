/**
 * @module SecretRefField — Picker for a `name/key` reference to one entry of a
 * registered secret.
 *
 * The stored form is a single string, so this renders two controls over it: a
 * modal table for the secret and a select for the entry within it. The secret
 * side is a dialog rather than a second select because a tenant's secrets are
 * an open-ended set — the old select pulled all of them into one dropdown, so
 * it grew unusable long before it silently truncated. {@link RecordPickerDialog}
 * pages, sorts, and filters them server-side instead, exactly as the group and
 * member pickers do. The entry side stays a select: those are the keys of a
 * single secret, which is not a set that grows without bound.
 *
 * Entry keys come from `listSecretKeys`, not from the secret's own `keys`
 * field, because that field only ever reports a `local` secret's entries — a
 * `vault` secret's keys live at its KV v2 path and are read live. Going through
 * the endpoint for both kinds keeps one code path and always shows keys as they
 * are right now.
 *
 * Only the *chosen* secret is fetched here, by name, and only the dialog ever
 * lists the rest — so mounting this field costs one narrow lookup rather than a
 * download of the whole secret set.
 *
 * A reference is resolved lazily at clone time, so a secret can be renamed or
 * deleted out from under a stored value. When that has happened the value is
 * never silently dropped: it stays selected, labelled `(not found)`, with a
 * warning — clearing it is the user's call, not this component's.
 */
"use client";

import { KeyRound } from "lucide-react";
import type React from "react";
import { useEffect, useState } from "react";
import { FormField } from "@/components/admin/form-field";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { RecordPickerDialog } from "@/components/admin/record-picker-dialog";
import { tagsColumn } from "@/components/admin/tag-columns";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import type { ColumnDef } from "@/components/ui/data-table";
import { Select, type SelectOption } from "@/components/ui/select";
import { useTags } from "@/hooks/useTags";
import { listSecretKeys, listSecrets, type Secret } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Label of the entry select's "no entry chosen" option. */
const NONE_LABEL = "None";

/** Props for {@link SecretPickerDialog}. */
interface SecretPickerDialogProps {
  open: boolean;
  onClose: () => void;
  /** Called with the chosen secret's name, or `""` if the dialog was cleared. */
  onAssign: (name: string) => void;
  panelId: string;
  /** Currently referenced secret name, or `""` when none is chosen. */
  value: string;
}

/**
 * {@link RecordPickerDialog} configured for secrets, columned like the Secrets
 * list page minus the columns that don't help a picker: the name is plain text
 * rather than a link (this dialog does not navigate away from a half-filled
 * form), and the audit/action columns describe bookkeeping the operator is not
 * picking on. Type is dropped too — an operator is choosing *which* secret to
 * use, not sorting by storage backend — while Tags stays and is filterable,
 * since tags are how a tenant with many secrets narrows down to the one it
 * wants.
 *
 * A component of its own, not inlined into {@link SecretRefField}, so
 * `useTags` — like {@link RecordPickerDialog}'s own row fetch — only runs once
 * the picker has actually been opened, not on every mount of the field.
 */
function SecretPickerDialog({ open, onClose, onAssign, panelId, value }: SecretPickerDialogProps) {
  const { byId: tagsById } = useTags();
  const columns: ColumnDef<Secret>[] = [
    {
      header: "Name",
      sortField: "name",
      filterField: "name",
      visibility: "always",
      cell: (secret) => secret.name,
    },
    {
      header: "Description",
      cell: (secret) => secret.description || "—",
    },
    tagsColumn<Secret>((secret) => secret.tagIds, tagsById),
  ];

  return (
    <RecordPickerDialog<Secret>
      open={open}
      onClose={onClose}
      onAssign={(ids) => onAssign(ids[0] ?? "")}
      panelId={panelId}
      title="Select secret"
      // Keyed by name, not id: a reference stores the secret's name, and
      // resolving it is deferred to clone time.
      value={value === "" ? [] : [value]}
      multiple={false}
      listRecords={listSecrets}
      columns={columns}
      getId={(secret) => secret.name}
      getLabel={(secret) => secret.name}
      emptyMessage="This tenant has no secrets yet."
      emptyIcon={KeyRound}
    />
  );
}

/**
 * Split a `name/key` reference into its parts, mirroring the backend's
 * `split_secret_ref`: only the first `/` separates, so a key may contain one.
 *
 * @param ref - The reference to split, possibly empty.
 * @returns The secret name and the entry key, either of which may be empty.
 */
function splitRef(ref: string): [name: string, key: string] {
  const slash = ref.indexOf("/");
  return slash === -1 ? [ref, ""] : [ref.slice(0, slash), ref.slice(slash + 1)];
}

/** Props for {@link SecretRefField}. */
export interface SecretRefFieldProps {
  /** Current `name/key` reference, or `""` when nothing is referenced. */
  value: string;
  /**
   * Called with the new `name/key`, or `""` whenever the pair is incomplete —
   * a secret with no entry chosen yet is not a usable reference.
   */
  onChange: (value: string) => void;
  /** Label of the secret picker. The entry select is always labelled "Entry Key". */
  label: string;
  /** Prefix for the DOM ids of the entry select and the dialog panel. */
  idPrefix: string;
  /** Explanatory text rendered under the pair. */
  hint?: React.ReactNode;
  /** Validation message from the surrounding form, shown under the secret chip. */
  error?: string;
  /** Hides the select button and the chip's remove button, and disables the entry select. */
  disabled?: boolean;
}

/**
 * Picker for one entry of a registered secret, covering both `local` and
 * `vault` secrets.
 */
export function SecretRefField({
  value,
  onChange,
  label,
  idPrefix,
  hint,
  error,
  disabled = false,
}: SecretRefFieldProps) {
  const [keys, setKeys] = useState<string[]>([]);
  const [keysFailed, setKeysFailed] = useState(false);
  // Id of the secret `name` resolves to, and whether the lookup has positively
  // established that no such secret is registered. The two are separate because
  // "not looked up yet" and "not there" must not read alike: only the latter
  // may brand a stored value `(not found)`.
  const [selectedId, setSelectedId] = useState<string | undefined>(undefined);
  const [nameMissing, setNameMissing] = useState(false);
  const [open, setOpen] = useState(false);
  const [everOpened, setEverOpened] = useState(false);
  // Holds the secret while no entry is chosen yet, which `value` cannot express
  // (an incomplete pair is reported to the form as ""). Once the pair is
  // complete, `value` is authoritative again.
  const [pendingName, setPendingName] = useState("");

  const [refName, refKey] = splitRef(value);
  const name = value === "" ? pendingName : refName;

  // Resolve just the chosen secret, by name. The id is what `listSecretKeys`
  // needs, and an empty result is what marks the reference as dangling.
  useEffect(() => {
    // Cleared synchronously, before the request is even made, so the keys
    // effect below never runs one render against the *previous* secret's id.
    // Left to settle asynchronously it would fetch that secret's entries under
    // the new name, and a former single-entry secret would auto-complete the
    // reference with a key the new one may not even have.
    setSelectedId(undefined);
    setNameMissing(false);
    if (name === "") return;
    let cancelled = false;
    listSecrets({ limit: 1, filters: [{ field: "name", op: "eq", value: name }] })
      .then((found) => {
        if (cancelled) return;
        setSelectedId(found[0]?.id);
        setNameMissing(found.length === 0);
      })
      .catch(() => {
        // Failure toast is shown globally by api.ts. Leaving `nameMissing`
        // false keeps a stored value from being branded "not found" merely
        // because the lookup could not be made.
      });
    return () => {
      cancelled = true;
    };
  }, [name]);

  useEffect(() => {
    if (selectedId === undefined) {
      setKeys([]);
      setKeysFailed(false);
      return;
    }
    let cancelled = false;
    listSecretKeys(selectedId)
      .then((fetched) => {
        if (cancelled) return;
        setKeys(fetched);
        setKeysFailed(false);
      })
      .catch(() => {
        // A vault secret's keys need Vault to be reachable; when it is not, the
        // stored key is kept and the failure is surfaced inline (and as the
        // global toast from api.ts).
        if (cancelled) return;
        setKeys([]);
        setKeysFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  // A secret holding exactly one entry leaves nothing to choose, so complete
  // the reference rather than making the user pick the only option.
  useEffect(() => {
    if (name === "" || refKey !== "" || keys.length !== 1) return;
    onChange(`${name}/${keys[0]}`);
  }, [name, refKey, keys, onChange]);

  const keyUnlisted = refKey !== "" && !keys.includes(refKey);
  const keyMissing = keyUnlisted && keys.length > 0;

  // An unlisted key is always offered, whether or not it is known to be gone:
  // a select can only display a value it has an option for.
  const keyOptions: SelectOption[] = [
    { value: "", label: NONE_LABEL },
    ...(keyUnlisted
      ? [{ value: refKey, label: keyMissing ? `${refKey} (not found)` : refKey }]
      : []),
    ...keys.map((key) => ({ value: key, label: key })),
  ];

  let warning: string | null = null;
  if (nameMissing) {
    warning = `No secret named "${name}" is registered. This will fail when it is used.`;
  } else if (keysFailed) {
    warning = `Could not list the entries of "${name}". The stored key is kept as it is.`;
  } else if (keyMissing) {
    warning = `Secret "${name}" has no entry "${refKey}". This will fail when it is used.`;
  }

  /** Apply a newly chosen secret, dropping the entry chosen under the old one. */
  function handleName(next: string) {
    if (next === name) return;
    setPendingName(next);
    onChange("");
  }

  /** Apply a newly chosen entry, completing or clearing the reference. */
  function handleKey(next: string) {
    onChange(next === "" || name === "" ? "" : `${name}/${next}`);
  }

  /** Opens the picker dialog, mounting it on the first call. */
  function openPicker() {
    setEverOpened(true);
    setOpen(true);
  }

  return (
    <div className="flex flex-col gap-1.5">
      {name === "" ? (
        // Nothing is chosen yet, so there is nothing for the Entry Key select
        // to offer either — showing it disabled next to an empty placeholder
        // just doubled the empty state. Collapse to the one control that
        // actually does something: the button that starts a pick.
        <div className="flex flex-col gap-1.5">
          <span className="text-label-caps">{label}</span>
          {disabled ? (
            <ReadOnlyField>{EMPTY_VALUE}</ReadOnlyField>
          ) : (
            <div>
              <Button type="button" variant="secondary" onClick={openPicker}>
                Select secret…
              </Button>
            </div>
          )}
          {error && <p className="text-xs text-error">{error}</p>}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {/* Deliberately not a FormField: its `<label htmlFor>` would become
              the accessible name of whatever it points at, renaming the
              "Select secret…" button to the field's label. RecordPickerField
              renders the same span-plus-error pair, for the same reason. */}
          <div className="flex flex-col gap-1.5">
            <span className="text-label-caps">{label}</span>
            <div className="flex flex-wrap gap-1.5">
              <Chip
                label={nameMissing ? `${name} (not found)` : name}
                onRemove={disabled ? undefined : () => handleName("")}
                size="lg"
              />
            </div>
            {!disabled && (
              <div>
                <Button type="button" variant="secondary" onClick={openPicker}>
                  Select secret…
                </Button>
              </div>
            )}
            {error && <p className="text-xs text-error">{error}</p>}
          </div>
          <FormField htmlFor={`${idPrefix}Key`} label="Entry Key">
            <Select
              id={`${idPrefix}Key`}
              options={keyOptions}
              value={refKey}
              onChange={handleKey}
              disabled={disabled}
            />
          </FormField>
        </div>
      )}
      {warning && <p className="text-xs text-error">{warning}</p>}
      {hint && <p className="text-xs text-on-surface-variant">{hint}</p>}
      {/* Mounted on the first open and then kept mounted, so the secret list
          costs nothing until asked for and the leave animation still has a
          component to run on. */}
      {everOpened && (
        <SecretPickerDialog
          open={open}
          onClose={() => setOpen(false)}
          onAssign={(secretName) => {
            handleName(secretName);
            setOpen(false);
          }}
          panelId={`${idPrefix}-secret-picker-dialog`}
          value={name}
        />
      )}
    </div>
  );
}
