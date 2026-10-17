"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Home, Users, History, Settings, FolderTree, ListChecks } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api, type Job } from "@/lib/api";
import { BrandMark } from "@/components/BrandMark";

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
    // Shortcut: keep polling only while there is an active job. When
    // the queue is idle the indicator is just a dot — polling for it
    // every 5s forever is pure waste (3 clients × 17k reqs/day each).
    // When a job appears we resume polling so the badge stays live.
    refetchInterval: (query) => (query.state.data?.job ? 5_000 : false),
  });
  const hasActive = !!data?.job;

  return (
    <aside className="hidden md:flex w-64 flex-col border-r border-border bg-card p-4">
      {/* Logo + brand */}
      <Link
        href="/"
        className="flex items-center gap-3 mb-8 px-2 rounded-md hover:bg-muted transition-colors"
      >
        <BrandMark />
        <div className="leading-tight">
          <div className="font-display text-[15px] font-semibold tracking-[-0.02em]">
            Dnload <span className="font-normal">Social</span>
          </div>
          <div className="text-[11px] text-muted-foreground">Local · Multi-platform</div>
        </div>
      </Link>

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
                "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <Icon
                className={cn(
                  "h-4 w-4 transition-colors",
                  active ? "text-primary-foreground" : "text-muted-foreground group-hover:text-foreground"
                )}
              />
              <span className="flex-1">{l.label}</span>
              {isJobs && hasActive && (
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-success" />
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer status badge — matches ảnh's server health pill style */}
      <div className="mt-4 rounded-lg border border-border bg-background p-3">
        <div className="flex items-center gap-2 text-xs">
          <span className="h-1.5 w-1.5 rounded-full bg-success" />
          <span className="text-foreground">Local-first</span>
          <span className="ml-auto text-muted-foreground">100% offline</span>
        </div>
      </div>
    </aside>
  );
}
