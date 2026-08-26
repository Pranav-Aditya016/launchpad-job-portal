"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Upload" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/sources", label: "Sources" },
  { href: "/connections", label: "Connections" },
];

// Sticky glass chrome, content scrolls under it (nav-glass in globals.css).
// The active link gets a spring-animated pill (motion layoutId) that slides
// between tabs instead of popping — see apple-design skill §12.
export function NavBar() {
  const pathname = usePathname();
  return (
    <header className="nav-glass no-print sticky top-0 z-40">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-3 sm:px-6 sm:py-3.5">
        <Link
          href="/"
          className="font-display text-headline tracking-[-0.01em] text-foreground shrink-0"
        >
          LaunchPad
        </Link>
        {/* overflow-x-auto rather than wrap or truncate: on a narrow phone
            every tab stays reachable via a horizontal swipe instead of
            silently falling off the edge of the screen. */}
        <nav className="flex items-center gap-0.5 overflow-x-auto sm:gap-1">
          {LINKS.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "pressable relative shrink-0 rounded-full px-2.5 py-1 text-[0.8125rem] font-medium transition-colors duration-150 sm:px-3.5 sm:py-1.5 sm:text-[0.875rem]",
                  active ? "text-accent-foreground" : "text-muted hover:text-foreground"
                )}
              >
                {active && (
                  <motion.span
                    layoutId="nav-active-pill"
                    className="absolute inset-0 rounded-full bg-accent"
                    style={{ boxShadow: "0 2px 10px rgba(124, 92, 255, 0.35)" }}
                    transition={{ type: "spring", bounce: 0.2, duration: 0.5 }}
                  />
                )}
                <span className="relative">{link.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
