import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SFM — Stock Pick Dashboard",
  description: "Daily stock indicator dashboard for 3:59 PM picks",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
