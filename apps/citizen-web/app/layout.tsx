import type { Metadata, Viewport } from "next";

import { AuthProvider } from "@/components/AuthProvider";
import { SiteHeader } from "@/components/SiteHeader";

import "./globals.css";

export const metadata: Metadata = {
  title: "RAKSHA NET AI — Report an emergency",
  description:
    "Report an emergency with your location and track the status of your report.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Reporting happens one-handed, outdoors, under stress. Never block zoom.
  maximumScale: 5,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <AuthProvider>
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-brand-600 focus:px-4 focus:py-2 focus:text-white"
          >
            Skip to content
          </a>
          <SiteHeader />
          <main id="main" className="mx-auto w-full max-w-3xl px-4 py-8">
            {children}
          </main>
          <footer className="muted mx-auto w-full max-w-3xl px-4 pb-10 text-xs">
            <p>
              RAKSHA NET AI is a decision-support platform. In a life-threatening
              emergency, always call your national emergency number as well.
            </p>
          </footer>
        </AuthProvider>
      </body>
    </html>
  );
}
