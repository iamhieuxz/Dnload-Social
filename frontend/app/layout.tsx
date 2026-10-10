import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Sidebar } from "@/components/Sidebar";
import { ActiveJobIndicator } from "@/components/ActiveJobIndicator";
import { QueryProvider } from "./providers";
import { Sparkles } from "lucide-react";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "IG Downloader — Local Server",
  description: "Manage Instagram media downloads locally",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} ${mono.variable} font-sans antialiased`}>
        <QueryProvider>
          <div className="flex min-h-screen">
            <Sidebar />
            <div className="flex-1 flex flex-col min-w-0">
              <header className="sticky top-0 z-20 border-b border-white/5 bg-background/60 backdrop-blur-xl px-6 py-3 flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="hidden sm:flex h-2 w-2 rounded-full bg-success pulse-glow" />
                  <div>
                    <div className="text-sm font-semibold flex items-center gap-2">
                      <Sparkles className="h-3.5 w-3.5 text-primary" />
                      Local Instagram Downloader
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      Self-hosted · SQLite · FastAPI + Next.js
                    </div>
                  </div>
                </div>
                <ActiveJobIndicator />
              </header>
              <main className="flex-1 p-6 max-w-[1600px] w-full mx-auto">{children}</main>
            </div>
          </div>
        </QueryProvider>
      </body>
    </html>
  );
}
