"use client";

import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";

/**
 * One place that decides how motion behaves.
 *
 * `reducedMotion="user"` makes every `motion.*` element in the app drop its
 * transform and layout animations when the operating system asks for reduced
 * motion, keeping only opacity changes. The shared timing lives here too, so
 * transitions feel like one product rather than a dozen.
 */
export function MotionProvider({ children }: { children: ReactNode }) {
  return (
    <MotionConfig
      reducedMotion="user"
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </MotionConfig>
  );
}
