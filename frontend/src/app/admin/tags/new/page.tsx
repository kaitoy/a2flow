/**
 * @module NewTagPage — Admin form for creating a tag.
 *
 * The tenant a tag belongs to is not picked here — it comes from the app bar's
 * tenant picker (`auth.selectedTenantId`), the same tenant every other request
 * already acts as, exactly as the new-user-group form does it.
 */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Tags } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { TagColorField } from "@/components/admin/tag-color-field";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { zTagCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { createTag, type TagColor } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { DEFAULT_TAG_COLOR } from "@/lib/tag-palette";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// `color` is a controlled select rendered with a live preview, so it is kept
// out of the form state like every other non-input control in this codebase.
const schema = zTagCreate.omit({ color: true });

type FormValues = z.input<typeof schema>;

export default function NewTagPage() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [color, setColor] = useState<TagColor>(DEFAULT_TAG_COLOR);
  const isSuperAdminViewer = useHasRole(Role.SUPER_ADMIN);
  const canEdit = useHasRole(Role.ADMIN, Role.DEVELOPER);
  const selectedTenantId = useAppSelector((s) => s.auth.selectedTenantId);
  // A tenant-scoped viewer's own tenant is applied server-side regardless, so
  // only a super admin's app-bar selection is ever meaningful here.
  const tenantMissing = isSuperAdminViewer && selectedTenantId === null;

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: { name: "" },
  });

  async function onSubmit(values: FormValues) {
    try {
      await save.run(async () => {
        await createTag({ name: values.name, color });
        dispatch(showToast({ message: "Tag created" }));
        router.push("/admin/tags");
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Tags", href: "/admin/tags" },
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
      <AdminPageHeader title="New Tag" icon={Tags} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
            <Input id="name" placeholder="e.g. production" {...register("name")} />
          </FormField>

          <TagColorField value={color} onChange={setColor} previewLabel={watch("name")} />

          {tenantMissing && (
            <p className="text-xs text-error">
              Select a tenant in the header before creating this tag.
            </p>
          )}

          <div className="flex gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={save.inFlight || tenantMissing}
              status={save.status}
              pendingLabel="Saving…"
            >
              Save
            </Button>
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/tags")}>
              Cancel
            </Button>
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}
