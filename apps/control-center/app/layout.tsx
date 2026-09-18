import type { Metadata, Viewport } from "next";

import { AuthProvider } from "@/components/AuthProvider";
import { ConsoleHeader } from "@/components/ConsoleHeader";

import "./globals.css";

export const metadata: Metadata = {
  title: "RAKSHA NET AI — Control Centre",
  description: "Emergency incident triage, prioritisation and coordination.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <AuthProvider>
          <ConsoleHeader />
          <main id="main" className="mx-auto w-full max-w-[110rem] px-4 py-6">
            {children}
          </main>
        </AuthProvider>
      </body>
    </html>
  );
}
