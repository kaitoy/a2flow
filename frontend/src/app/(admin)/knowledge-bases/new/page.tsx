/** @module NewKnowledgeBasePage — Admin form for creating a knowledge base. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { BookOpen } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import {
  emptyKnowledgeBaseFormValues,
  KnowledgeBaseFields,
  type KnowledgeBaseFormValues,
  knowledgeBaseFormSchema,
  toKnowledgeBaseBody,
} from "@/components/admin/knowledge-base-fields";
import { TagPicker } from "@/components/admin/tag-picker";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useT } from "@/i18n/provider";
import { createKnowledgeBase, setKnowledgeBaseTags } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/**
 * Admin page creating an empty knowledge base. Sources are added on the
 * knowledge base's own page, which the form opens once it is saved.
 */
export default function NewKnowledgeBasePage() {
  const t = useT();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const canEdit = useHasRole(Role.DEVELOPER);
  // Tags live outside the form state: they are a sub-resource written after
  // the knowledge base exists.
  const [tagIds, setTagIds] = useState<string[]>([]);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<KnowledgeBaseFormValues>({
    resolver: zodResolver(knowledgeBaseFormSchema),
    mode: "onBlur",
    defaultValues: emptyKnowledgeBaseFormValues(),
  });

  async function onSubmit(values: KnowledgeBaseFormValues) {
    try {
      await save.run(async () => {
        const created = await createKnowledgeBase(toKnowledgeBaseBody(values));
        if (tagIds.length > 0) {
          await setKnowledgeBaseTags(created.id, tagIds);
        }
        dispatch(showToast({ message: t("knowledgeBases.knowledgeBaseCreated") }));
        router.push(`/knowledge-bases/${created.id}`);
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: t("common.home"), href: "/" },
    { label: t("common.knowledgeBases"), href: "/knowledge-bases" },
    { label: t("common.new") },
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
      <AdminPageHeader title={t("knowledgeBases.newKnowledgeBase")} icon={BookOpen} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <KnowledgeBaseFields register={register} errors={errors} showPlaceholders />

          <TagPicker value={tagIds} onChange={setTagIds} />

          <div className="flex gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={save.inFlight}
              status={save.status}
              pendingLabel={t("common.saving")}
            >
              {t("common.save")}
            </Button>
            <Button type="button" variant="ghost" onClick={() => router.push("/knowledge-bases")}>
              {t("common.cancel")}
            </Button>
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}
