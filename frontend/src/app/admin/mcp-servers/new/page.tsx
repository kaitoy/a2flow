/** @module NewMcpServerPage — Admin form for registering a new MCP server. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Server } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";
import { useForm } from "react-hook-form";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import {
  emptyMcpServerFormValues,
  McpServerFields,
  type McpServerFormValues,
  mcpServerFormSchema,
  toMcpServerBody,
} from "@/components/admin/mcp-server-fields";
import { Button } from "@/components/ui/button";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { createMcpServer } from "@/lib/api";
import { parsePrefill } from "@/lib/mcp-registry-prefill";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/** The create form itself; reads registry prefill from the URL search params. */
function NewMcpServerForm() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const searchParams = useSearchParams();

  // Seed the form from registry prefill query params (set by the registry search
  // dialog); falls back to empty values for a manual entry.
  const defaultValues = useMemo<McpServerFormValues>(() => {
    const prefill = parsePrefill(searchParams);
    return { ...emptyMcpServerFormValues(), ...prefill };
  }, [searchParams]);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    control,
    watch,
    formState: { errors },
  } = useForm<McpServerFormValues>({
    resolver: zodResolver(mcpServerFormSchema),
    mode: "onBlur",
    defaultValues,
  });
  const transport = watch("transport");

  async function onSubmit(values: McpServerFormValues) {
    try {
      await save.run(async () => {
        await createMcpServer(toMcpServerBody(values));
        dispatch(showToast({ message: "MCP server created" }));
        router.push("/admin/mcp-servers");
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
          <McpServerFields
            register={register}
            control={control}
            errors={errors}
            transport={transport}
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
 * Admin page for registering a new MCP server.
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
