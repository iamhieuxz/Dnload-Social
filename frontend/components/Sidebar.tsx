"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Home, Users, History, Settings, Download, Sparkles, FolderTree, ListChecks } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api, type Job } from "@/lib/api";

const links = [
  { href: "/", label: "Dashboard", icon: Home },
  { href: "/downloads", label: "Downloads", icon: ListChecks },
  { href: "/gallery", label: "Gallery", icon: FolderTree },
  { href: "/accounts", label: "Accounts", icon: Users },
  { href: "/jobs", label: "Jobs", icon: History },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const path = usePathname();

  const { data } = useQuery<{ job: Job | null }>({
    queryKey: ["active-job"],
    queryFn: async () => (await api.get("/api/jobs/active")).data,
    refetchInterval: 5_000,
  });
  const hasActive = !!data?.job;

  return (
    <aside className="hidden md:flex w-64 flex-col border-r border-white/5 bg-card/40 backdrop-blur-xl p-4">
      <div className="flex items-center gap-3 mb-8 px-2">
        <div className="relative">
          <div className="absolute inset-0 bg-primary/40 blur-xl rounded-full" />
          <div className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-accent shadow-glow-sm">
            <Download className="h-5 w-5 text-white" />
          </div>
        </div>
        <div>
          <div className="text-base font-bold leading-tight gradient-text">IG Downloader</div>
          <div className="text-[10px] text-muted-foreground tracking-wider uppercase">v7.0.0</div>
        </div>
      </div>

      <nav className="space-y-1 flex-1">
        {links.map((l) => {
          const Icon = l.icon;
          const active = path === l.href || (l.href !== "/" && path.startsWith(l.href));
          const isJobs = l.href === "/jobs";
          return (
            <Link
              key={l.href}
              href={l.href}
              className={cn(
                "group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200",
                active
                  ? "bg-gradient-to-r from-primary/15 to-accent/10 text-foreground border border-primary/20 shadow-glow-sm"
                  : "text-muted-foreground hover:bg-white/5 hover:text-foreground"
              )}
            >
              <Icon
                className={cn(
                  "h-4 w-4 transition-colors",
                  active ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                )}
              />
              <span className="flex-1">{l.label}</span>
              {isJobs && hasActive && (
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="mt-4 rounded-lg border border-white/5 bg-gradient-to-br from-primary/5 to-accent/5 p-3">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          <span>Local-first · 100% offline</span>
        </div>
      </div>
    </aside>
  );
}
