/** @module NewSecretPage — Admin form for registering a new secret (local encrypted entries or Vault reference). */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { KeyRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import {
  buildSecretFormSchema,
  emptySecretFormValues,
  SecretFields,
  type SecretFormValues,
  toSecretBody,
} from "@/components/admin/secret-fields";
import { Button } from "@/components/ui/button";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { createSecret } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/** Creating a secret requires a value for every entry — nothing is stored yet to keep. */
const schema = buildSecretFormSchema(true);

export default function NewSecretPage() {
  const router = useRouter();
  const dispatch = useAppDispatch();

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    control,
    watch,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: emptySecretFormValues(),
  });
  const type = watch("type");

  async function onSubmit(values: SecretFormValues) {
    try {
      await save.run(async () => {
        await createSecret(toSecretBody(values));
        dispatch(showToast({ message: "Secret created" }));
        router.push("/admin/secrets");
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Secrets", href: "/admin/secrets" },
          { label: "New" },
        ]}
      />
      <AdminPageHeader title="New Secret" icon={KeyRound} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <SecretFields
            register={register}
            control={control}
            errors={errors}
            type={type}
            showPlaceholders
          />

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
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/secrets")}>
              Cancel
            </Button>
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}
