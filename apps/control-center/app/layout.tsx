import type { Metadata, Viewport } from "next";

import { AuthProvider } from "@/components/AuthProvider";
import { MotionProvider } from "@/components/animations/MotionProvider";

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

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">
        <MotionProvider>
          <AuthProvider>{children}</AuthProvider>
        </MotionProvider>
      </body>
    </html>
  );
}
