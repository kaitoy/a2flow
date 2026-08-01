/** @module FormLayout — Two-column shell for admin detail (edit) pages. */
import type { ReactNode } from "react";

/** Props for {@link FormLayout}. */
export interface FormLayoutProps {
  /** The page header, typically an `AdminPageHeader`. Sits above the form. */
  header: ReactNode;
  /** The form card and any panels that belong beside it, in the main column. */
  children: ReactNode;
  /** Secondary read-only content for the narrow trailing column, e.g. `AuditMeta`. */
  aside?: ReactNode;
}

/**
 * Shell for admin detail/edit pages: a header row, the form card below it, and a
 * narrow trailing column for read-only metadata.
 *
 * Once the surrounding content area reaches `@4xl` (56rem) the layout splits into
 * a fluid main column plus a fixed 16rem aside; below that everything stacks and
 * the main column narrows to `max-w-2xl`, which is exactly how these pages looked
 * before the split. The breakpoint is a container query rather than a viewport
 * one because the admin shell reserves a 256px sidebar, so viewport width
 * overstates how much room the page actually has.
 *
 * The header is placed inside the main column on purpose: its right-hand action
 * cluster then lines up with the form's right edge instead of the page's, so
 * page-level actions read as belonging to the form rather than to the aside.
 *
 * Both column tracks come from the grid template rather than from the items, so
 * the main column keeps its width while asynchronously loaded metadata is still
 * in flight and nothing reflows once it arrives. Create pages, which have no
 * metadata to show, use `FormColumn` instead.
 */
export function FormLayout({ header, children, aside }: FormLayoutProps) {
  return (
    <div className="@container">
      <div className="grid gap-x-6 @4xl:grid-cols-[minmax(0,1fr)_16rem]">
        <div className="min-w-0 @4xl:col-start-1 @4xl:row-start-1">{header}</div>
        <div className="mx-auto w-full min-w-0 max-w-2xl @4xl:col-start-1 @4xl:row-start-2 @4xl:max-w-none">
          {children}
        </div>
        {aside && (
          <aside className="mx-auto mt-4 w-full min-w-0 max-w-2xl @4xl:col-start-2 @4xl:row-start-2 @4xl:mt-0 @4xl:max-w-none @4xl:self-start">
            {aside}
          </aside>
        )}
      </div>
    </div>
  );
}
