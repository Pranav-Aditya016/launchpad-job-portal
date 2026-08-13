"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Upload" },
  { href: "/dashboard", label: "Dashboard" },
];

// Translucent, content-scrolls-under chrome (material() in globals.css) rather
// than an opaque bar — see apple-design skill §12.
export function NavBar() {
  const pathname = usePathname();
  return (
    <header className="material no-print sticky top-0 z-40 border-b border-[color:var(--border)]">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3.5">
        <Link href="/" className="text-headline tracking-[-0.01em]">
          LaunchPad
        </Link>
        <nav className="flex items-center gap-1">
          {LINKS.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "pressable rounded-lg px-3 py-1.5 text-[0.875rem] font-medium transition-colors duration-150",
                  active ? "bg-[color:var(--accent-wash)] text-accent" : "text-muted hover:text-foreground"
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
