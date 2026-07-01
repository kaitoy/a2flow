/** @module NewUserPage — Admin form for creating a new application user. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Users as UsersIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ErrorBanner } from "@/components/admin/error-banner";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { zUserCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { createUser } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

const schema = zUserCreate;

type FormValues = z.infer<typeof schema>;

export default function NewUserPage() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [apiError, setApiError] = useState<string | null>(null);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: {
      username: "",
      firstName: "",
      lastName: "",
      password: "",
      email: "",
      enabled: true,
      emailVerified: false,
    },
  });

  async function onSubmit(values: FormValues) {
    setApiError(null);
    try {
      await save.run(async () => {
        await createUser({
          username: values.username,
          firstName: values.firstName,
          lastName: values.lastName,
          password: values.password,
          email: values.email,
          enabled: values.enabled,
          emailVerified: values.emailVerified,
        });
        dispatch(showToast({ message: "User created" }));
        router.push("/admin/users");
      });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to create user");
    }
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Users", href: "/admin/users" },
          { label: "New" },
        ]}
      />
      <AdminPageHeader title="New User" icon={UsersIcon} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="username" label="Username" required error={errors.username?.message}>
            <Input id="username" placeholder="e.g. alice" {...register("username")} />
          </FormField>

          <FormField
            htmlFor="firstName"
            label="First Name"
            required
            error={errors.firstName?.message}
          >
            <Input id="firstName" placeholder="Alice" {...register("firstName")} />
          </FormField>

          <FormField htmlFor="lastName" label="Last Name" required error={errors.lastName?.message}>
            <Input id="lastName" placeholder="Smith" {...register("lastName")} />
          </FormField>

          <FormField htmlFor="email" label="Email" required error={errors.email?.message}>
            <Input id="email" type="email" placeholder="alice@example.com" {...register("email")} />
          </FormField>

          <FormField htmlFor="password" label="Password" required error={errors.password?.message}>
            <Input
              id="password"
              type="password"
              placeholder="At least 12 characters"
              {...register("password")}
            />
          </FormField>

          <Checkbox label="Enabled" {...register("enabled")} />
          <Checkbox label="Email verified" {...register("emailVerified")} />

          <ErrorBanner error={apiError} />

          <div className="flex gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={save.inFlight}
              status={save.status}
              pendingLabel="Saving…"
            >
              Save
            </Button>
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/users")}>
              Cancel
            </Button>
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}
