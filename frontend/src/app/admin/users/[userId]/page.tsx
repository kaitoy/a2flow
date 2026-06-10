/** @module UserDetailPage — Admin edit/view form for an existing user. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { ErrorBanner } from "@/components/admin/error-banner";
import { FormField } from "@/components/admin/form-field";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { deleteUser, getUser, type UserUpdate, updateUser } from "@/lib/api";

const schema = z.object({
  firstName: z.string().min(1, "First name is required"),
  lastName: z.string().min(1, "Last name is required"),
  // Optional on edit: a blank value leaves the stored password unchanged.
  password: z
    .string()
    .refine((v) => v === "" || v.length >= 12, "Password must be at least 12 characters"),
  email: z.string().email("Must be a valid email"),
  enabled: z.boolean(),
  emailVerified: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

export default function EditUserPage() {
  const { userId } = useParams<{ userId: string }>();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  // Username is immutable after creation, so it lives outside the form state and
  // is rendered read-only.
  const [username, setUsername] = useState("");

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: {
      firstName: "",
      lastName: "",
      password: "",
      email: "",
      enabled: true,
      emailVerified: false,
    },
  });

  useEffect(() => {
    getUser(userId)
      .then((user) => {
        setUsername(user.username);
        reset({
          firstName: user.firstName,
          lastName: user.lastName,
          password: "",
          email: user.email,
          enabled: user.enabled,
          emailVerified: user.emailVerified,
        });
        setAudit({
          createdBy: user.createdBy,
          updatedBy: user.updatedBy,
          createdAt: user.createdAt,
          updatedAt: user.updatedAt,
        });
      })
      .catch((e: unknown) => {
        setApiError(e instanceof Error ? e.message : "Failed to load user");
      })
      .finally(() => setLoading(false));
  }, [userId, reset]);

  async function onSubmit(values: FormValues) {
    setApiError(null);
    const body: UserUpdate = {
      firstName: values.firstName,
      lastName: values.lastName,
      email: values.email,
      enabled: values.enabled,
      emailVerified: values.emailVerified,
    };
    if (values.password) {
      body.password = values.password;
    }
    try {
      await updateUser(userId, body);
      router.push("/admin/users");
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to update user");
    }
  }

  function handleDelete() {
    setConfirmOpen(true);
  }

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteUser(userId);
      router.push("/admin/users");
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to delete user");
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl p-8">
        <h1 className="mb-6 text-3xl font-semibold tracking-tight text-gradient-accent">
          Edit User
        </h1>
        <FormSkeleton fields={6} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl p-8">
      <h1 className="mb-6 text-3xl font-semibold tracking-tight text-gradient-accent">Edit User</h1>

      <form
        onSubmit={handleSubmit(onSubmit)}
        className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
      >
        <FormField htmlFor="username" label="Username">
          <Input id="username" value={username} readOnly disabled />
        </FormField>

        <FormField
          htmlFor="firstName"
          label="First Name"
          required
          error={errors.firstName?.message}
        >
          <Input id="firstName" {...register("firstName")} />
        </FormField>

        <FormField htmlFor="lastName" label="Last Name" required error={errors.lastName?.message}>
          <Input id="lastName" {...register("lastName")} />
        </FormField>

        <FormField htmlFor="email" label="Email" required error={errors.email?.message}>
          <Input id="email" type="email" {...register("email")} />
        </FormField>

        <FormField htmlFor="password" label="Password" error={errors.password?.message}>
          <Input
            id="password"
            type="password"
            placeholder="Leave blank to keep unchanged"
            {...register("password")}
          />
        </FormField>

        <Checkbox label="Enabled" {...register("enabled")} />
        <Checkbox label="Email verified" {...register("emailVerified")} />

        <ErrorBanner error={apiError} />

        <div className="flex gap-2">
          <Button type="submit" variant="primary" disabled={isSubmitting}>
            {isSubmitting ? "Saving…" : "Save"}
          </Button>
          <Button type="button" variant="ghost" onClick={() => router.push("/admin/users")}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={handleDelete}
            className="ml-auto text-error"
          >
            Delete
          </Button>
        </div>
      </form>
      {audit && (
        <div className="mt-4">
          <AuditMeta {...audit} />
        </div>
      )}
      <ConfirmDialog
        open={confirmOpen}
        title="Delete User"
        description={`Delete "${username}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
