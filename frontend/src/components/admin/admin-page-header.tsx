import Link from "next/link";

interface AdminPageHeaderProps {
  title: string;
  addHref?: string;
  addLabel?: string;
}

/** Admin list-page header with a title and an optional "Add" link button. */
export function AdminPageHeader({ title, addHref, addLabel }: AdminPageHeaderProps) {
  return (
    <div className="mb-6 flex items-center justify-between">
      <h1 className="text-3xl font-semibold tracking-tight text-gradient-accent">{title}</h1>
      {addHref && addLabel && (
        <Link
          href={addHref}
          className={[
            "inline-flex cursor-pointer items-center gap-1 rounded-xl px-4 py-2",
            "text-sm font-medium tracking-tight text-on-primary",
            "bg-gradient-to-br from-accent to-secondary",
            "shadow-[0_4px_16px_-4px_var(--color-accent-soft),inset_0_1px_0_rgba(255,255,255,0.4)]",
            "transition-all duration-200 hover:-translate-y-0.5 hover:shadow-glow",
          ].join(" ")}
        >
          {addLabel}
        </Link>
      )}
    </div>
  );
}
