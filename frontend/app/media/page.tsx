"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type Media } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { useState } from "react";
import { formatBytes, formatNumber, cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { ChevronLeft, ChevronRight, Search, Image as ImageIcon, Film, Sparkles, FileText, Inbox } from "lucide-react";

const TYPES = [
  { value: "", label: "All", icon: ImageIcon },
  { value: "post", label: "Posts", icon: ImageIcon },
  { value: "story", label: "Stories", icon: Sparkles },
  { value: "highlight", label: "Highlights", icon: Film },
];

const mediaIcon = (t: string) => {
  if (t === "post") return ImageIcon;
  if (t === "story") return Sparkles;
  if (t === "highlight") return Film;
  return FileText;
};

// All media tiles share the same neutral surface — no per-type color.
const mediaColor = (_t: string) => "bg-muted";

export default function MediaPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [type, setType] = useState<string>("");

  const { data, isLoading } = useQuery({
    queryKey: ["media", page, search, type],
    queryFn: async () =>
      (
        await api.get("/api/media", {
          params: {
            page,
            page_size: 60,
            search: search || undefined,
            media_type: type || undefined,
          },
        })
      ).data,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Media browser"
        description={`${formatNumber(data?.total ?? 0)} files indexed`}
      />

      <Card className="p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search filenames..."
              value={search}
              onChange={(e) => {
                setPage(1);
                setSearch(e.target.value);
              }}
              className="pl-9 bg-background"
            />
          </div>
          <div className="flex gap-1">
            {TYPES.map((t) => {
              const Icon = t.icon;
              return (
                <button
                  key={t.value}
                  onClick={() => {
                    setPage(1);
                    setType(t.value);
                  }}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors border",
                    type === t.value
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {t.label}
                </button>
              );
            })}
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {formatNumber(data?.total ?? 0)} files · page {page}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="p-12 text-center text-muted-foreground">Loading...</div>
          ) : data?.items.length === 0 ? (
            <EmptyState
              icon={Inbox}
              title="Không tìm thấy file"
              description={search || type ? "Thử bỏ filter hoặc đổi từ khoá." : "Chưa có file nào trong DB."}
            />
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
              {data?.items.map((m: Media, i: number) => {
                const Icon = mediaIcon(m.media_type);
                return (
                  <a
                    key={m.id}
                    href={m.file_path}
                    target="_blank"
                    rel="noreferrer"
                    className="group relative overflow-hidden rounded-lg border border-border bg-card hover:border-foreground/30 transition-colors fade-in-up"
                    style={{ animationDelay: `${Math.min(i, 12) * 20}ms` }}
                  >
                    <div
                      className={cn(
                        "aspect-square flex items-center justify-center relative overflow-hidden",
                        mediaColor(m.media_type)
                      )}
                    >
                      <Icon className="h-8 w-8 text-muted-foreground group-hover:text-foreground group-hover:scale-110 transition-all" />
                      <Badge
                        variant="outline"
                        className="absolute top-1.5 right-1.5 text-[9px] bg-card/80 border-border"
                      >
                        {m.media_type}
                      </Badge>
                    </div>
                    <div className="p-2">
                      <div className="text-xs font-medium truncate" title={m.file_name}>
                        {m.file_name}
                      </div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">
                        {formatBytes(m.file_size_bytes)}
                      </div>
                    </div>
                  </a>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2">
        <Button
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page === 1}
          variant="outline"
          size="sm"
        >
          <ChevronLeft className="h-4 w-4" /> Prev
        </Button>
        <Button
          onClick={() => setPage((p) => p + 1)}
          disabled={!data || page * 60 >= data.total}
          variant="outline"
          size="sm"
        >
          Next <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
