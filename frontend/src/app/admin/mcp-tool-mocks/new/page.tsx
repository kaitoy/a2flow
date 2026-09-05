/** @module NewMcpToolMockPage — Admin form for registering a new tool mock. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { FlaskConical } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import {
  emptyMcpToolMockFormValues,
  McpToolMockFields,
  type McpToolMockFormValues,
  mcpToolMockFormSchema,
  toMcpToolMockBody,
} from "@/components/admin/mcp-tool-mock-fields";
import { TagPicker } from "@/components/admin/tag-picker";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { createMcpToolMock, setMcpToolMockTags } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/** Admin page for registering a new tool mock. */
export default function NewMcpToolMockPage() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const canEdit = useHasRole(Role.DEVELOPER);

  // Tags live outside the form state: the picker is a controlled multi-select
  // rather than a registered input, and tags are a sub-resource written after
  // the mock exists.
  const [tagIds, setTagIds] = useState<string[]>([]);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    control,
    watch,
    formState: { errors },
  } = useForm<McpToolMockFormValues>({
    resolver: zodResolver(mcpToolMockFormSchema),
    mode: "onBlur",
    defaultValues: emptyMcpToolMockFormValues(),
  });
  const target = watch("target");

  async function onSubmit(values: McpToolMockFormValues) {
    try {
      await save.run(async () => {
        const created = await createMcpToolMock(toMcpToolMockBody(values));
        if (tagIds.length > 0) {
          await setMcpToolMockTags(created.id, tagIds);
        }
        dispatch(showToast({ message: "Tool mock created" }));
        router.push("/admin/mcp-tool-mocks");
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Tool Mocks", href: "/admin/mcp-tool-mocks" },
    { label: "New" },
  ];

  // The list page hides Add for this viewer, so reaching the form at all means a
  // deep link; refuse it here rather than let the submit 403.
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
      <AdminPageHeader title="New Tool Mock" icon={FlaskConical} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <McpToolMockFields
            register={register}
            control={control}
            errors={errors}
            target={target}
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
            <Button
              type="button"
              variant="ghost"
              onClick={() => router.push("/admin/mcp-tool-mocks")}
            >
              Cancel
            </Button>
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}
