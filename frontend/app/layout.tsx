import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { Inter, Inter_Tight, JetBrains_Mono } from "next/font/google";
import { Sidebar } from "@/components/Sidebar";
import { ActiveJobIndicator } from "@/components/ActiveJobIndicator";
import { ScrollToTopButton } from "@/components/ScrollToTopButton";
import { BrandMark } from "@/components/BrandMark";
import { CommandPaletteHost } from "@/components/CommandPaletteHost";
import { QueryProvider } from "./providers";
import "./globals.css";

const inter = Inter({ subsets: ["latin", "vietnamese"], variable: "--font-inter" });
const interTight = Inter_Tight({ subsets: ["latin", "vietnamese"], variable: "--font-inter-tight" });
const mono = JetBrains_Mono({ subsets: ["latin", "vietnamese"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "Dnload Social — Local",
  applicationName: "Dnload Social",
  description: "Local-first download manager for Instagram, Twitter / X and TikTok",
  icons: {
    // Versioned URLs on purpose: Chrome keeps stale favicons for the old
    // unversioned /favicon.ico, so bump ?v= whenever the artwork changes.
    icon: [
      { url: "/brand/favicon.svg?v=2", type: "image/svg+xml", sizes: "any" },
      { url: "/favicon.ico?v=2", type: "image/x-icon", sizes: "16x16 32x32 48x48" },
    ],
    apple: { url: "/brand/apple-touch-icon.png?v=2", sizes: "180x180", type: "image/png" },
  },
};

export const viewport: Viewport = {
  themeColor: "#0B0B0E",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className="dark">
      <body className={`${inter.variable} ${interTight.variable} ${mono.variable} font-sans antialiased`}>
        <QueryProvider>
          <div className="flex min-h-screen">
            <Sidebar />
            <div className="flex-1 flex flex-col min-w-0">
              <header className="sticky top-0 z-20 flex items-center justify-between gap-4 border-b border-border bg-background px-6 py-3">
                <Link
                  href="/"
                  aria-label="Dnload Social — về Dashboard"
                  className="-m-2 flex items-center gap-2 rounded-md p-2 md:hidden"
                >
                  <BrandMark className="h-7 w-7" />
                  <span className="hidden font-display text-sm font-semibold tracking-[-0.02em] sm:inline">
                    Dnload <span className="font-normal">Social</span>
                  </span>
                </Link>
                <div className="hidden md:block" />
                <ActiveJobIndicator />
              </header>
              <main className="flex-1 p-6 max-w-[1600px] w-full mx-auto">{children}</main>
            </div>
          </div>
          <ScrollToTopButton />
          <CommandPaletteHost />
        </QueryProvider>
      </body>
    </html>
  );
}
