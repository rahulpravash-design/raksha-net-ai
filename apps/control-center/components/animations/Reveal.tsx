"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

/**
 * Fade-and-rise entrance, optionally staggered by `index`.
 *
 * Short on purpose (under 400 ms in total): an entrance animation must never
 * delay an operator from reading or acting. Under reduced motion the provider
 * strips the movement and leaves a plain fade.
 */
export function Reveal({
  children,
  index = 0,
  className,
  as = "div",
}: {
  children: ReactNode;
  index?: number;
  className?: string;
  as?: "div" | "section" | "li" | "aside";
}) {
  const Component = motion[as];
  return (
    <Component
      className={className}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index, 8) * 0.05 }}
    >
      {children}
    </Component>
  );
}
