import Link from "next/link";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-surface">
      <nav className="flex w-60 shrink-0 flex-col border-r border-outline-variant bg-surface-container-low">
        <div className="border-b border-outline-variant px-4 py-4">
          <span className="text-sm font-semibold text-on-surface">Admin</span>
        </div>
        <ul className="py-2">
          <li>
            <Link
              href="/admin/agent-skills"
              className="block px-4 py-2 text-sm text-on-surface-variant hover:bg-surface-container"
            >
              Agent Skills
            </Link>
          </li>
        </ul>
        <div className="mt-auto border-t border-outline-variant px-4 py-4">
          <Link href="/" className="text-xs text-on-surface-variant hover:text-primary">
            ← Back to chat
          </Link>
        </div>
      </nav>
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
