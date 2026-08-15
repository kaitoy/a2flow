/** @module NewSecretPage — Admin form for registering a new secret (local encrypted entries or Vault reference). */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { KeyRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
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
import { TagPicker } from "@/components/admin/tag-picker";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { createSecret, setSecretTags } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/** Creating a secret requires a value for every entry — nothing is stored yet to keep. */
const schema = buildSecretFormSchema(true);

export default function NewSecretPage() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const canEdit = useHasRole(Role.ADMIN, Role.DEVELOPER);

  // Tags live outside the form state: the picker is a controlled
  // multi-select rather than a registered input.
  const [tagIds, setTagIds] = useState<string[]>([]);

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
        const created = await createSecret(toSecretBody(values));
        // Tags are a sub-resource of the record, so they can only be
        // written once it exists.
        if (tagIds.length > 0) {
          await setSecretTags(created.id, tagIds);
        }
        dispatch(showToast({ message: "Secret created" }));
        router.push("/admin/secrets");
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Secrets", href: "/admin/secrets" },
    { label: "New" },
  ];

  // The list page hides the Add button for this viewer, so reaching the form at
  // all means a deep link; refuse it here rather than let the submit 403.
  if (!canEdit) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
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

          <TagPicker value={tagIds} onChange={setTagIds} />

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
