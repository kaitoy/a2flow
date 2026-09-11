/**
 * @module admin-loading — the one skeleton every admin route's `loading.tsx` renders.
 *
 * An admin page is a breadcrumb trail, a header, and either a table or a form,
 * so its loading fallback is the same three things with placeholders in the
 * body. Each route's `loading.tsx` passes just what differs: the trail after
 * "Admin", the icon and title, and either the table's columns or the form's
 * field count.
 */

import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { AdminListSkeleton } from "./admin-list-skeleton";
import { AdminPageContainer } from "./admin-page-container";
import { AdminPageHeader } from "./admin-page-header";
import { type BreadcrumbItem, Breadcrumbs } from "./breadcrumbs";
import { FormColumn } from "./form-column";
import { FormLayout } from "./form-layout";
import { FormSkeleton } from "./form-skeleton";

/** Props for {@link AdminLoading}. */
export interface AdminLoadingProps {
  /** Breadcrumb items after the leading "Admin" crumb, which is always prepended. */
  crumbs: BreadcrumbItem[];
  /** Icon shown in the page header. */
  icon: LucideIcon;
  /** Header title; detail pages leave it out because the real title is the record's name. */
  title?: string;
  /** Href of the header's add button, for list pages that have one. */
  addHref?: string;
  /** Label of the header's add button. */
  addLabel?: string;
  /** Column headers of a list page's table; when set, the body is a table skeleton. */
  columns?: string[];
  /** Number of placeholder fields in a form page's body. */
  fields?: number;
  /**
   * Which form shell wraps the fields: `"layout"` is the detail page's
   * {@link FormLayout} (header inside the shell), `"column"` the create page's
   * {@link FormColumn} (header above it).
   */
  form?: "layout" | "column";
}

/**
 * Skeleton of an admin page: the real breadcrumbs and header over a placeholder
 * table or form.
 *
 * @param props - See {@link AdminLoadingProps}.
 * @returns The loading fallback.
 */
export function AdminLoading({
  crumbs,
  icon,
  title,
  addHref,
  addLabel,
  columns,
  fields = 4,
  form = "layout",
}: AdminLoadingProps) {
  const header = (
    <AdminPageHeader title={title} icon={icon} addHref={addHref} addLabel={addLabel} />
  );
  let body: ReactNode;
  if (columns) {
    body = (
      <>
        {header}
        <AdminListSkeleton columns={columns} />
      </>
    );
  } else if (form === "column") {
    body = (
      <>
        {header}
        <FormColumn>
          <FormSkeleton fields={fields} />
        </FormColumn>
      </>
    );
  } else {
    body = (
      <FormLayout header={header}>
        <FormSkeleton fields={fields} />
      </FormLayout>
    );
  }
  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, ...crumbs]} />
      {body}
    </AdminPageContainer>
  );
}
