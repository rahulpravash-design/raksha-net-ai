import type { Metadata, Viewport } from "next";
import { connection } from "next/server";

import { ApiConfigNotice } from "@raksha/ui";

import { AuthProvider } from "@/components/AuthProvider";
import { MotionProvider } from "@/components/animations/MotionProvider";
import { API_CONFIG } from "@/lib/config";

import "./globals.css";

export const metadata: Metadata = {
  title: "RAKSHA NET AI — Control Centre",
  description: "Emergency incident triage, prioritisation and coordination.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#050914",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // Every page is rendered per request so it can carry this request's CSP nonce
  // (proxy.ts); a prerendered page would have no nonce and its scripts would not run.
  await connection();
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">
        <ApiConfigNotice
          message={API_CONFIG.ok ? null : API_CONFIG.problem.message}
        />
        <MotionProvider>
          <AuthProvider>{children}</AuthProvider>
        </MotionProvider>
      </body>
    </html>
  );
}
