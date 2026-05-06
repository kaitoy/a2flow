import Link from "next/link";

interface AdminPageHeaderProps {
  title: string;
  addHref: string;
  addLabel: string;
}

export function AdminPageHeader({ title, addHref, addLabel }: AdminPageHeaderProps) {
  return (
    <div className="mb-6 flex items-center justify-between">
      <h1 className="text-2xl font-semibold text-on-surface">{title}</h1>
      <Link
        href={addHref}
        className="inline-flex cursor-pointer items-center rounded bg-primary-container px-4 py-2 text-sm font-medium text-on-primary-container transition-colors hover:bg-primary"
      >
        {addLabel}
      </Link>
    </div>
  );
}
