"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { api, type OverviewStats } from "@/lib/api";
import { formatBytes, formatNumber } from "@/lib/utils";
import { Users, Image, HardDrive, Activity, TrendingUp } from "lucide-react";

type CardDef = {
  title: string;
  value: string;
  sub: string;
  icon: typeof Users;
  gradient: string;
  iconBg: string;
  trend?: number;
};

const buildCards = (stats: OverviewStats): CardDef[] => [
  {
    title: "Accounts",
    value: formatNumber(stats.total_accounts),
    sub: `${formatNumber(stats.total_posts)} posts · ${formatNumber(stats.total_stories)} stories`,
    icon: Users,
    gradient: "from-primary/20 via-primary/5 to-transparent",
    iconBg: "bg-primary/20 text-primary",
  },
  {
    title: "Total Media",
    value: formatNumber(stats.total_media),
    sub: "Indexed in local database",
    icon: Image,
    gradient: "from-accent/20 via-accent/5 to-transparent",
    iconBg: "bg-accent/20 text-accent",
  },
  {
    title: "Disk Usage",
    value: formatBytes(stats.total_size_bytes),
    sub: "Stored on download folder",
    icon: HardDrive,
    gradient: "from-warning/20 via-warning/5 to-transparent",
    iconBg: "bg-warning/20 text-warning",
  },
  {
    title: "Jobs (24h)",
    value: `${stats.jobs_completed_24h} / ${stats.jobs_failed_24h + stats.jobs_completed_24h}`,
    sub: `${stats.jobs_running} running now`,
    icon: Activity,
    gradient: "from-success/20 via-success/5 to-transparent",
    iconBg: "bg-success/20 text-success",
  },
];

export function StatCards() {
  const { data, isLoading } = useQuery<OverviewStats>({
    queryKey: ["stats-overview"],
    queryFn: async () => (await api.get("/api/stats/overview")).data,
    refetchInterval: 5_000,
  });

  if (isLoading || !data) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i} variant="glass">
            <CardContent className="p-5 space-y-3">
              <div className="h-4 w-24 shimmer rounded" />
              <div className="h-8 w-16 shimmer rounded" />
              <div className="h-3 w-32 shimmer rounded" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {buildCards(data).map((c, idx) => {
        const Icon = c.icon;
        return (
          <Card
            key={c.title}
            variant="glass"
            className="group relative overflow-hidden hover:border-white/20 transition-all hover:-translate-y-0.5 hover:shadow-glow-sm fade-in-up"
            style={{ animationDelay: `${idx * 60}ms` }}
          >
            <div
              className={`absolute inset-0 bg-gradient-to-br ${c.gradient} opacity-60 group-hover:opacity-100 transition-opacity pointer-events-none`}
            />
            <CardContent className="relative p-5 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {c.title}
                </span>
                <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${c.iconBg}`}>
                  <Icon className="h-4 w-4" />
                </div>
              </div>
              <div className="text-3xl font-bold tracking-tight">{c.value}</div>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <TrendingUp className="h-3 w-3" />
                <span className="truncate">{c.sub}</span>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
