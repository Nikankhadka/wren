import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

// Inter (variable font) is self-hosted by next/font and exposed as the
// --font-inter CSS variable, which theme.css picks up for --font-sans and
// --font-display. First build fetches the font once over the network.
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Wren",
  description:
    "A private, branded AI support and sales agent for any business.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`h-full antialiased ${inter.variable}`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
