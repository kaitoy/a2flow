/**
 * @module SystemSettingsPage — Admin page for the platform-wide system settings.
 *
 * A single record rather than a collection, so there is no create/edit split and
 * no shared `*-fields.tsx`: this page is the only consumer of the shape.
 */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Settings2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormField } from "@/components/admin/form-field";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { SegmentedControl, type SegmentedOption } from "@/components/ui/segmented-control";
import { zSystemSettingsUpdate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  getSystemSettings,
  type SmtpSecurity,
  SUPPRESS_FORBIDDEN_TOAST,
  type SystemSettingsUpdate,
  sendSmtpTestEmail,
  updateSystemSettings,
} from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/** How the connection to the relay is secured, in the order operators reach for them. */
const SECURITY_OPTIONS: ReadonlyArray<SegmentedOption<SmtpSecurity>> = [
  { value: "starttls", label: "STARTTLS" },
  { value: "ssl", label: "SSL/TLS" },
  { value: "none", label: "None" },
];

/**
 * Check a value the form keeps as a plain string against a generated field
 * schema, skipping the check when it is empty.
 *
 * The generated schemas are all nullish, so an empty input passes them by
 * definition. The form holds these fields as plain strings and decides
 * requiredness itself (see {@link buildSchema}), deferring to the generated
 * schema only for the format constraints.
 */
function validateOptional(
  value: string,
  schema: z.ZodType,
  ctx: z.RefinementCtx,
  path: string
): void {
  if (value === "") return;
  const result = schema.safeParse(value);
  if (!result.success) {
    ctx.addIssue({ code: "custom", path: [path], message: result.error.issues[0].message });
  }
}

/**
 * Build the validation schema, mirroring the merged-result rules the backend
 * applies in `SystemSettingsService`.
 *
 * `passwordSet` is a parameter rather than a form field: whether a password is
 * already stored decides whether leaving the field blank is acceptable, and the
 * value itself is never sent to the client.
 */
function buildSchema(passwordSet: boolean) {
  return z
    .object({
      appBaseUrl: z.string(),
      smtpEnabled: z.boolean(),
      smtpHost: z.string(),
      smtpPort: z.string(),
      smtpSecurity: z.enum(["none", "starttls", "ssl"]),
      smtpUsername: z.string(),
      smtpPassword: z.string(),
      smtpFromEmail: z.string(),
      smtpFromName: z.string(),
    })
    .superRefine((values, ctx) => {
      validateOptional(
        values.appBaseUrl,
        zSystemSettingsUpdate.shape.appBaseUrl,
        ctx,
        "appBaseUrl"
      );
      validateOptional(values.smtpHost, zSystemSettingsUpdate.shape.smtpHost, ctx, "smtpHost");
      validateOptional(
        values.smtpUsername,
        zSystemSettingsUpdate.shape.smtpUsername,
        ctx,
        "smtpUsername"
      );
      validateOptional(
        values.smtpFromEmail,
        zSystemSettingsUpdate.shape.smtpFromEmail,
        ctx,
        "smtpFromEmail"
      );
      validateOptional(
        values.smtpFromName,
        zSystemSettingsUpdate.shape.smtpFromName,
        ctx,
        "smtpFromName"
      );

      const port = Number(values.smtpPort);
      if (!Number.isInteger(port) || port < 1 || port > 65535) {
        ctx.addIssue({
          code: "custom",
          path: ["smtpPort"],
          message: "Port must be a whole number between 1 and 65535",
        });
      }

      if (values.smtpEnabled) {
        if (values.smtpHost === "") {
          ctx.addIssue({
            code: "custom",
            path: ["smtpHost"],
            message: "Host is required when email delivery is enabled",
          });
        }
        if (values.smtpFromEmail === "") {
          ctx.addIssue({
            code: "custom",
            path: ["smtpFromEmail"],
            message: "From address is required when email delivery is enabled",
          });
        }
      }

      if (values.smtpUsername !== "" && values.smtpPassword === "" && !passwordSet) {
        ctx.addIssue({
          code: "custom",
          path: ["smtpPassword"],
          message: "Password is required when a username is set",
        });
      }
    });
}

type FormValues = z.infer<ReturnType<typeof buildSchema>>;

/** Blank values, used until the saved settings have loaded. */
function emptyFormValues(): FormValues {
  return {
    appBaseUrl: "",
    smtpEnabled: false,
    smtpHost: "",
    smtpPort: "587",
    smtpSecurity: "starttls",
    smtpUsername: "",
    smtpPassword: "",
    smtpFromEmail: "",
    smtpFromName: "",
  };
}

/**
 * Build the PATCH body.
 *
 * Cleared text fields are sent as `null` so clearing one actually clears it,
 * while an untouched password field is omitted entirely — the backend then keeps
 * the ciphertext it already holds.
 */
function toBody(values: FormValues): SystemSettingsUpdate {
  const body: SystemSettingsUpdate = {
    appBaseUrl: values.appBaseUrl || null,
    smtpEnabled: values.smtpEnabled,
    smtpHost: values.smtpHost || null,
    smtpPort: Number(values.smtpPort),
    smtpSecurity: values.smtpSecurity,
    smtpUsername: values.smtpUsername || null,
    smtpFromEmail: values.smtpFromEmail || null,
    smtpFromName: values.smtpFromName || null,
  };
  if (values.smtpPassword !== "") {
    body.smtpPassword = values.smtpPassword;
  }
  return body;
}

/**
 * The PATCH body for "Clear SMTP settings": every SMTP field back to its
 * default, delivery disabled, and the stored password explicitly wiped.
 *
 * `appBaseUrl` is deliberately absent — it isn't an SMTP field, so it is left
 * untouched. `smtpPassword: null` only reaches the backend through this
 * dedicated action: a blank form field always omits the key instead (see
 * {@link toBody}), so `null` is unambiguously "clear it" here.
 */
const CLEARED_SMTP_BODY: SystemSettingsUpdate = {
  smtpEnabled: false,
  smtpHost: null,
  smtpPort: 587,
  smtpSecurity: "starttls",
  smtpUsername: null,
  smtpPassword: null,
  smtpFromEmail: null,
  smtpFromName: null,
};

/**
 * The platform-wide settings: the SMTP relay notification email is delivered
 * through, and the base URL those messages link back to. Reachable only by
 * `super_admin` — `layout.tsx` blocks every other viewer before this page
 * mounts.
 */
export default function SystemSettingsPage() {
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  // Whether a password is stored. Drives both the placeholder and the
  // "username needs a password" rule, since the value itself never arrives.
  const [passwordSet, setPasswordSet] = useState(false);
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);

  const save = useAsyncAction({ showDone: false });
  const test = useAsyncAction();
  const clear = useAsyncAction({ showDone: false });
  const schema = useMemo(() => buildSchema(passwordSet), [passwordSet]);

  const {
    register,
    handleSubmit,
    reset,
    getValues,
    control,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: emptyFormValues(),
  });

  useEffect(() => {
    getSystemSettings(SUPPRESS_FORBIDDEN_TOAST)
      .then((settings) => {
        setPasswordSet(settings.smtpPasswordSet ?? false);
        // Every field is listed: one left out here would be silently cleared on
        // the next save, since `toBody` sends the whole record.
        reset({
          appBaseUrl: settings.appBaseUrl ?? "",
          smtpEnabled: settings.smtpEnabled ?? false,
          smtpHost: settings.smtpHost ?? "",
          smtpPort: String(settings.smtpPort ?? 587),
          smtpSecurity: settings.smtpSecurity ?? "starttls",
          smtpUsername: settings.smtpUsername ?? "",
          smtpPassword: "",
          smtpFromEmail: settings.smtpFromEmail ?? "",
          smtpFromName: settings.smtpFromName ?? "",
        });
        setAudit({
          createdBy: settings.createdBy,
          updatedBy: settings.updatedBy,
          createdAt: settings.createdAt,
          updatedAt: settings.updatedAt,
        });
      })
      .catch(() => {
        setDenied(true);
      })
      .finally(() => setLoading(false));
  }, [reset]);

  async function onSubmit(values: FormValues) {
    try {
      await save.run(async () => {
        const saved = await updateSystemSettings(toBody(values));
        setPasswordSet(saved.smtpPasswordSet ?? false);
        // The password is write-only, so the field goes back to blank: what is
        // stored is reported by the placeholder, not by the input's value.
        reset({ ...values, smtpPassword: "" });
        dispatch(showToast({ message: "System settings updated" }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function onSendTest() {
    try {
      await test.run(async () => {
        await sendSmtpTestEmail();
        dispatch(showToast({ message: "Test email sent" }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function executeClear() {
    setConfirmClearOpen(false);
    try {
      await clear.run(async () => {
        const saved = await updateSystemSettings(CLEARED_SMTP_BODY);
        setPasswordSet(saved.smtpPasswordSet ?? false);
        reset({ ...emptyFormValues(), appBaseUrl: getValues("appBaseUrl") });
        dispatch(showToast({ message: "SMTP settings cleared" }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [{ label: "Admin", href: "/admin" }, { label: "System Settings" }];
  const header = <AdminPageHeader title="System Settings" icon={Settings2} />;

  if (loading) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={header}>
          <FormSkeleton fields={8} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  if (denied) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={header}>
          <p className="rounded-2xl glass-panel-strong p-6 text-on-surface-variant">
            The system settings could not be loaded.
          </p>
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout header={header} aside={audit && <AuditMeta {...audit} />}>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField
            htmlFor="appBaseUrl"
            label="Application Base URL"
            error={errors.appBaseUrl?.message}
          >
            <Input
              id="appBaseUrl"
              placeholder="https://a2flow.example.com"
              {...register("appBaseUrl")}
            />
            <p className="text-xs text-on-surface-variant">
              Where notification email links back to. Leave empty to send messages without a link.
            </p>
          </FormField>

          <hr className="border-outline-variant" />

          <Checkbox label="Send notifications by email" {...register("smtpEnabled")} />

          <FormField htmlFor="smtpHost" label="SMTP Host" error={errors.smtpHost?.message}>
            <Input id="smtpHost" placeholder="smtp.example.com" {...register("smtpHost")} />
          </FormField>

          <FormField htmlFor="smtpPort" label="SMTP Port" error={errors.smtpPort?.message}>
            <Input id="smtpPort" inputMode="numeric" {...register("smtpPort")} />
          </FormField>

          <FormField htmlFor="smtpSecurity" label="Security">
            <Controller
              name="smtpSecurity"
              control={control}
              render={({ field }) => (
                <SegmentedControl
                  options={SECURITY_OPTIONS}
                  value={field.value}
                  onChange={field.onChange}
                  aria-label="Connection security"
                />
              )}
            />
          </FormField>

          <FormField
            htmlFor="smtpUsername"
            label="SMTP Username"
            error={errors.smtpUsername?.message}
          >
            <Input id="smtpUsername" {...register("smtpUsername")} />
            <p className="text-xs text-on-surface-variant">
              Leave empty for a relay that does not require authentication.
            </p>
          </FormField>

          <FormField
            htmlFor="smtpPassword"
            label="SMTP Password"
            error={errors.smtpPassword?.message}
          >
            <PasswordInput
              id="smtpPassword"
              autoComplete="new-password"
              placeholder={passwordSet ? "Saved — leave empty to keep it" : ""}
              {...register("smtpPassword")}
            />
          </FormField>

          <FormField
            htmlFor="smtpFromEmail"
            label="From Address"
            error={errors.smtpFromEmail?.message}
          >
            <Input
              id="smtpFromEmail"
              placeholder="a2flow@example.com"
              {...register("smtpFromEmail")}
            />
          </FormField>

          <FormField htmlFor="smtpFromName" label="From Name" error={errors.smtpFromName?.message}>
            <Input id="smtpFromName" placeholder="A2Flow" {...register("smtpFromName")} />
          </FormField>

          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={save.inFlight}
              status={save.status}
              pendingLabel="Saving…"
            >
              Save
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={onSendTest}
              disabled={test.inFlight}
              status={test.status}
              pendingLabel="Sending…"
              doneLabel="Sent"
            >
              Send test email
            </Button>
            <Button
              type="button"
              variant="danger"
              onClick={() => setConfirmClearOpen(true)}
              disabled={clear.inFlight}
              status={clear.status}
              pendingLabel="Clearing…"
            >
              Clear SMTP settings
            </Button>
          </div>
          <p className="text-xs text-on-surface-variant">
            The test message uses the <em>saved</em> settings and goes to your own address. Save
            first if you have just changed something.
          </p>
        </form>
      </FormLayout>
      <ConfirmDialog
        open={confirmClearOpen}
        title="Clear SMTP Settings"
        description="This clears the SMTP host, credentials, and sender address, and disables email delivery. This cannot be undone."
        onConfirm={executeClear}
        onCancel={() => setConfirmClearOpen(false)}
        confirmLabel="Clear"
      />
    </AdminPageContainer>
  );
}
