/**
 * @module SecretRefField — Picker for a `name/key` reference to one entry of a
 * registered secret.
 *
 * The stored form is a single string, so this renders two selects over it: one
 * for the secret and one for the entry within it. Entry keys come from
 * `listSecretKeys`, not from the secret's own `keys` field, because that field
 * only ever reports a `local` secret's entries — a `vault` secret's keys live
 * at its KV v2 path and are read live. Going through the endpoint for both
 * kinds keeps one code path and always shows keys as they are right now.
 *
 * A reference is resolved lazily at clone time, so a secret can be renamed or
 * deleted out from under a stored value. When that has happened the value is
 * never silently dropped: it stays selected, labelled `(not found)`, with a
 * warning — clearing it is the user's call, not this component's.
 */
"use client";

import type React from "react";
import { useEffect, useState } from "react";
import { FormField } from "@/components/admin/form-field";
import { Select, type SelectOption } from "@/components/ui/select";
import { listSecretKeys, listSecrets, type Secret } from "@/lib/api";

/** How many secrets to offer. Far above any realistic per-tenant count. */
const SECRET_LIMIT = 200;

/** Label of the entry meaning "no reference at all". */
const NONE_LABEL = "None";

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
  /** Label of the secret select. The entry select is always labelled "Entry Key". */
  label: string;
  /** Prefix for the two selects' DOM ids, so their labels can point at them. */
  idPrefix: string;
  /** Explanatory text rendered under the pair. */
  hint?: React.ReactNode;
  /** Validation message from the surrounding form, shown on the secret select. */
  error?: string;
  /** Disables both selects. */
  disabled?: boolean;
}

/**
 * Two-select picker for one entry of a registered secret, covering both `local`
 * and `vault` secrets.
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
  const [secrets, setSecrets] = useState<Secret[]>([]);
  const [secretsLoaded, setSecretsLoaded] = useState(false);
  const [keys, setKeys] = useState<string[]>([]);
  const [keysFailed, setKeysFailed] = useState(false);
  // Holds the secret while no entry is chosen yet, which `value` cannot express
  // (an incomplete pair is reported to the form as ""). Once the pair is
  // complete, `value` is authoritative again.
  const [pendingName, setPendingName] = useState("");

  const [refName, refKey] = splitRef(value);
  const name = value === "" ? pendingName : refName;

  useEffect(() => {
    let cancelled = false;
    listSecrets({ limit: SECRET_LIMIT, sort: { field: "name", descending: false } })
      .then((fetched) => {
        if (cancelled) return;
        setSecrets(fetched);
        setSecretsLoaded(true);
      })
      .catch(() => {
        // Failure toast is shown globally by api.ts. Leaving `secretsLoaded`
        // false keeps a stored value from being branded "not found" merely
        // because the list could not be fetched.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedId = secrets.find((secret) => secret.name === name)?.id;

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

  const nameUnlisted = name !== "" && !secrets.some((secret) => secret.name === name);
  const nameMissing = nameUnlisted && secretsLoaded;
  const keyUnlisted = refKey !== "" && !keys.includes(refKey);
  const keyMissing = keyUnlisted && keys.length > 0;

  // An unlisted value is always offered, whether or not it is known to be gone:
  // a select can only display a value it has an option for.
  const secretOptions: SelectOption[] = [
    { value: "", label: NONE_LABEL },
    ...(nameUnlisted ? [{ value: name, label: nameMissing ? `${name} (not found)` : name }] : []),
    ...secrets.map((secret) => ({ value: secret.name, label: secret.name })),
  ];

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

  return (
    <div className="flex flex-col gap-1.5">
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField htmlFor={`${idPrefix}Secret`} label={label} error={error}>
          <Select
            id={`${idPrefix}Secret`}
            options={secretOptions}
            value={name}
            onChange={handleName}
            disabled={disabled}
          />
        </FormField>
        <FormField htmlFor={`${idPrefix}Key`} label="Entry Key">
          <Select
            id={`${idPrefix}Key`}
            options={keyOptions}
            value={refKey}
            onChange={handleKey}
            disabled={disabled || name === ""}
          />
        </FormField>
      </div>
      {warning && <p className="text-xs text-error">{warning}</p>}
      {hint && <p className="text-xs text-on-surface-variant">{hint}</p>}
    </div>
  );
}
