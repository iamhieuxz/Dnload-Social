import type { Metadata } from "next";
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
  description: "Local-first download manager for Instagram, Twitter / X and TikTok",
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
                <div className="flex items-center gap-2 md:hidden">
                  <BrandMark className="h-7 w-7" />
                  <span className="font-display text-sm font-semibold tracking-[-0.02em]">
                    Dnload <span className="font-normal">Social</span>
                  </span>
                </div>
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
