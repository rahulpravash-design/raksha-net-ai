"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { isAdminRole } from "@raksha/api-client";

import { useAuth } from "@/components/AuthProvider";
import { seesIncidents } from "@/lib/routes";

const ITEMS = [
  {
    href: "/dashboard",
    label: "Command centre",
    match: (p: string) => p.startsWith("/dashboard") || p.startsWith("/incidents"),
    dispatchSide: true,
    adminOnly: false,
  },
  { href: "/resources", label: "Resources", match: (p: string) => p.startsWith("/resources"), dispatchSide: true, adminOnly: false },
  { href: "/hospitals", label: "Hospitals", match: (p: string) => p.startsWith("/hospitals"), dispatchSide: false, adminOnly: false },
  { href: "/admin/users", label: "Accounts", match: (p: string) => p.startsWith("/admin"), dispatchSide: false, adminOnly: true },
  { href: "/", label: "Overview", match: (p: string) => p === "/", dispatchSide: false, adminOnly: false },
];

/**
 * Module navigation. It lists only screens that exist; modules still to be
 * built (analytics) are not shown as links.
 * Rail on wide screens, a strip under the header on narrow ones.
 */
export function Sidebar() {
  const { user } = useAuth();
  const pathname = usePathname();
  if (!user) return null;

  return (
    <nav
      aria-label="Modules"
      className="flex flex-wrap gap-1 border-b border-[var(--border)] px-4 py-2 lg:sticky lg:top-0 lg:h-screen lg:w-52 lg:shrink-0 lg:flex-col lg:flex-nowrap lg:border-b-0 lg:border-r lg:px-3 lg:py-6"
    >
      <p className="muted mb-1 hidden px-3 text-[0.65rem] font-semibold uppercase tracking-[0.2em] lg:block">
        Modules
      </p>
      {ITEMS.filter((item) => (!item.dispatchSide || seesIncidents(user.role)) && (!item.adminOnly || isAdminRole(user.role))).map((item) => {
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
