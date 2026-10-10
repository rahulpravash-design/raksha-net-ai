"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/AuthProvider";

const ITEMS = [
  { href: "/dashboard", label: "Command centre", match: (p: string) => p.startsWith("/dashboard") || p.startsWith("/incidents") },
  { href: "/resources", label: "Resources", match: (p: string) => p.startsWith("/resources") },
  { href: "/", label: "Overview", match: (p: string) => p === "/" },
];

/**
 * Module navigation. It lists only screens that exist; modules still to be
 * built (hospitals, analytics) are not shown as links.
 * Rail on wide screens, a strip under the header on narrow ones.
 */
export function Sidebar() {
  const { user } = useAuth();
  const pathname = usePathname();
  if (!user) return null;

  return (
    <nav
      aria-label="Modules"
      className="flex gap-1 border-b border-[var(--border)] px-4 py-2 lg:sticky lg:top-0 lg:h-screen lg:w-52 lg:shrink-0 lg:flex-col lg:border-b-0 lg:border-r lg:px-3 lg:py-6"
    >
      <p className="muted mb-1 hidden px-3 text-[0.65rem] font-semibold uppercase tracking-[0.2em] lg:block">
        Modules
      </p>
      {ITEMS.map((item) => {
        const active = item.match(pathname);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className="relative rounded-lg px-3 py-2 text-sm font-medium transition-colors hover:bg-white/5"
          >
            {active && (
              <motion.span
                layoutId="nav-active"
                className="absolute inset-0 rounded-lg border border-[var(--accent)]/40 bg-[var(--accent)]/10"
              />
            )}
            <span className="relative">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
