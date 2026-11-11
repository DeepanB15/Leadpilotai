import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "LeadPilotAI", description: "Evidence-backed B2B company research" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
