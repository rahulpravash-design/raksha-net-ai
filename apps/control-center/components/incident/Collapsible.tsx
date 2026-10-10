"use client";

import { AnimatePresence, motion } from "motion/react";
import { useId, useState, type ReactNode } from "react";

/**
 * An expandable panel. The heading is a real button with `aria-expanded`, so it
 * works from the keyboard and is announced correctly; the body animates its
 * height briefly and is removed from the tree (not just hidden) when closed.
 */
export function Collapsible({
  title,
  summary,
  defaultOpen = true,
  children,
}: {
  title: string;
  /** Shown beside the title when collapsed, so the panel is never a mystery. */
  summary?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();

  return (
    <section className="panel-3d rounded-xl">
      <h2>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={() => setOpen((value) => !value)}
          className="flex w-full items-center justify-between gap-3 rounded-xl px-4 py-3 text-left font-semibold"
        >
          <span>{title}</span>
          <span className="flex items-center gap-2">
            {!open && summary && <span className="muted text-xs font-normal">{summary}</span>}
            <motion.svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="h-4 w-4"
              animate={{ rotate: open ? 180 : 0 }}
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="m6 9 6 6 6-6" />
            </motion.svg>
          </span>
        </button>
      </h2>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={bodyId}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
