/** @module NewMcpServerPage — Admin form for registering a new remote MCP server. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Server } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ErrorBanner } from "@/components/admin/error-banner";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import {
  KeyValueEditor,
  type KeyValuePair,
  pairsToRecord,
} from "@/components/admin/key-value-editor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { zMcpServerCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { createMcpServer } from "@/lib/api";
import { parsePrefill } from "@/lib/mcp-registry-prefill";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// Generated schema carries the name/url constraints; the form edits headers as
// an ordered key/value pair list (converted to a record on submit), so override
// that one field's shape while keeping the rest from the generated schema.
const schema = zMcpServerCreate.omit({ headers: true }).extend({
  headers: z.array(z.object({ key: z.string(), value: z.string() })),
});

type FormValues = z.infer<typeof schema>;

/** The create form itself; reads registry prefill from the URL search params. */
function NewMcpServerForm() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const searchParams = useSearchParams();
  const [apiError, setApiError] = useState<string | null>(null);

  // Seed the form from registry prefill query params (set by the registry search
  // dialog); falls back to empty values for a manual entry.
  const defaultValues = useMemo(() => {
    const prefill = parsePrefill(searchParams);
    return {
      name: prefill.name,
      url: prefill.url,
      headers: prefill.headers satisfies KeyValuePair[],
    };
  }, [searchParams]);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues,
  });

  async function onSubmit(values: FormValues) {
    setApiError(null);
    try {
      await save.run(async () => {
        await createMcpServer({
          name: values.name,
          url: values.url,
          headers: pairsToRecord(values.headers),
        });
        dispatch(showToast({ message: "MCP server created" }));
        router.push("/admin/mcp-servers");
      });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to create MCP server");
    }
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "MCP Servers", href: "/admin/mcp-servers" },
          { label: "New" },
        ]}
      />
      <AdminPageHeader title="New MCP Server" icon={Server} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
            <Input id="name" placeholder="e.g. web-search" {...register("name")} />
          </FormField>

          <FormField htmlFor="url" label="URL" required error={errors.url?.message}>
            <Input id="url" placeholder="https://mcp.example.com/mcp" {...register("url")} />
          </FormField>

          <FormField htmlFor="headers" label="HTTP Headers">
            <Controller
              control={control}
              name="headers"
              render={({ field }) => (
                <KeyValueEditor
                  name="headers"
                  pairs={field.value}
                  onChange={field.onChange}
                  keyPlaceholder="Authorization"
                  valuePlaceholder="Bearer …"
                />
              )}
            />
          </FormField>

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
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/mcp-servers")}>
              Cancel
            </Button>
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}

/**
 * Admin page for registering a new remote MCP server.
 *
 * Wraps the form in a Suspense boundary because it reads `useSearchParams` to
 * pick up registry prefill values.
 */
export default function NewMcpServerPage() {
  return (
    <Suspense>
      <NewMcpServerForm />
    </Suspense>
  );
}
