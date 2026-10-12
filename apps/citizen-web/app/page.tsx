"use client";

import Link from "next/link";

import { useAuth } from "@/components/AuthProvider";

const STEPS = [
  {
    title: "Describe what is happening",
    body: "Pick a category and tell us in your own words. A few sentences is enough.",
  },
  {
    title: "Share the location",
    body: "Use your device's location, or drop a pin on the map if it is not accurate.",
  },
  {
    title: "Track the response",
    body: "You get a reference code and can follow the status of your report.",
  },
];

export default function HomePage() {
  const { user, loading } = useAuth();

  return (
    <div className="space-y-10">
      <section className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Report an emergency and follow what happens next
        </h1>
        <p className="muted max-w-2xl">
          RAKSHA NET AI turns your report into structured, located information
          that an emergency control centre can act on. Every decision about a
          response is taken by a trained human operator.
        </p>

        <div className="flex flex-wrap gap-3">
          {loading ? null : user ? (
            <Link
              href="/report"
              className="rounded-lg bg-red-600 px-5 py-3 font-semibold text-white hover:bg-red-700"
            >
              Report an emergency
            </Link>
          ) : (
            <>
              <Link
                href="/register"
                className="rounded-lg bg-brand-600 px-5 py-3 font-semibold text-white hover:bg-brand-700"
              >
                Create an account
              </Link>
              <Link
                href="/login"
                className="surface rounded-lg px-5 py-3 font-semibold hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                Sign in
              </Link>
            </>
          )}
        </div>
      </section>

      <section
        aria-labelledby="how-it-works"
        className="grid gap-4 sm:grid-cols-3"
      >
        <h2 id="how-it-works" className="sr-only">
          How it works
        </h2>
        {STEPS.map((step, index) => (
          <article key={step.title} className="surface rounded-xl p-5">
            <span className="text-brand-600 text-sm font-bold">
              Step {index + 1}
            </span>
            <h3 className="mt-1 font-semibold">{step.title}</h3>
            <p className="muted mt-2 text-sm">{step.body}</p>
          </article>
        ))}
      </section>

      <section className="rounded-xl border border-amber-300 bg-amber-50 p-5 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
        <h2 className="font-semibold">If someone is in immediate danger</h2>
        <p className="mt-1">
          This platform is a pilot system. It does not replace your national
          emergency number — call it first, then file a report here so the
          control centre has your location and photographs.
        </p>
      </section>
    </div>
  );
}
