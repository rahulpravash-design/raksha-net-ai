"use client";

import Link from "next/link";

import { useAuth } from "@/components/AuthProvider";
import { featureAccess } from "@/lib/landing";

import { PLATFORM_FEATURES } from "./platformFeatures";

/**
 * What the platform does, one card per screen that exists. A card links to its
 * screen when the viewer may open it, to sign-in when they have not yet, and says
 * plainly when their role never could — rather than offering a link that would
 * only bounce them back.
 */
export function PlatformSection() {
  const { user, loading } = useAuth();
  const role = loading ? null : (user?.role ?? null);

  return (
    <section
      aria-labelledby="platform-heading"
      className="relative mx-auto w-full max-w-7xl px-5 py-16 sm:px-8"
    >
      <p className="text-xs font-semibold uppercase tracking-[0.25em] text-[var(--accent)]">
        The platform
      </p>
      <h2 id="platform-heading" className="mt-3 text-3xl font-extrabold tracking-tight sm:text-4xl">
        What it does, and who it is for
      </h2>
      <p className="muted mt-3 max-w-2xl text-sm leading-relaxed">
        Each of these is a working screen connected to the platform&rsquo;s API, behind sign-in and
        role checks. The 3D visuals are for orientation: they do not themselves provide emergency
        services, and the AI proposes while a trained person decides.
      </p>

      <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {PLATFORM_FEATURES.map((feature) => {
          const access = featureAccess(feature, role);
          return (
            <li key={feature.id} className="panel-3d flex flex-col rounded-xl p-5">
              <h3 className="text-base font-bold tracking-wide">{feature.title}</h3>
              <p className="muted mt-2 flex-1 text-sm leading-relaxed">{feature.summary}</p>
              <p className="mt-4 text-xs uppercase tracking-wider text-[var(--accent)]">
                {feature.audienceLabel}
              </p>
              <p className="mt-2 text-sm font-semibold">
                {access === "not-for-role" ? (
                  <span className="muted">Not available to your role</span>
                ) : (
                  <Link
                    href={feature.href}
                    className="text-[var(--accent)] underline-offset-4 hover:underline"
                  >
                    {access === "sign-in" ? "Sign in to open" : "Open"}
                    <span className="sr-only"> {feature.title}</span> →
                  </Link>
                )}
              </p>
            </li>
          );
        })}
      </ul>

      <p className="muted mt-8 text-xs">
        Citizens report through the citizen app and track only their own reports. Field crews work
        from the assignments dispatched to their unit in the responder app. Neither sees the
        incident queue.
      </p>
    </section>
  );
}
