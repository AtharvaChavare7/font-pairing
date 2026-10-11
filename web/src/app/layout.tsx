import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Font Pairing Engine",
  description: "Generate font pairings from real font geometry",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased bg-white text-gray-900">{children}</body>
    </html>
  );
}
