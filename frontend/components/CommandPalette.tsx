"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link2, Plus, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { detectUrl } from "@/lib/detect";
import { PlatformDot } from "@/components/PlatformDot";
import { ShortcutChip } from "@/components/ShortcutChip";
import { cn } from "@/lib/utils";

const PLATFORM_LABEL: Record<string, string> = {
  instagram: "Instagram",
  twitter: "Twitter / X",
  tiktok: "TikTok",
};

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * ⌘K / Ctrl+K quick-add palette (plan §6.1, §8).
 * Paste a URL → platform is detected from the host → one queued row is created.
 */
export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();

  const detected = useMemo(() => detectUrl(value), [value]);

  useEffect(() => {
    if (open) {
      setValue("");
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const addMut = useMutation({
    mutationFn: async () => {
      if (!detected?.platform) throw new Error("Link không thuộc Instagram, X hoặc TikTok");
      return (
        await api.post("/api/downloads/batch", {
          platform: detected.platform,
          source_type: "link",
          items: [{ url: detected.url, author: detected.author ?? undefined, content_type: detected.contentType ?? undefined }],
        })
      ).data;
    },
    onSuccess: (res) => {
      toast.success(`Đã thêm vào hàng đợi (${res.created})`);
      setValue("");
      qc.invalidateQueries({ queryKey: ["downloads"] });
      qc.invalidateQueries({ queryKey: ["downloads-stats"] });
      qc.invalidateQueries({ queryKey: ["pending-summary-all"] });
      onOpenChange(false);
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? e?.message ?? "Không thêm được"),
  });

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onOpenChange(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  if (!open) return null;

  const canSubmit = !!detected?.platform && !addMut.isPending;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-4 pt-[15vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onOpenChange(false);
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Thêm nhanh"
    >
      <div className="w-full max-w-xl overflow-hidden rounded-palette border border-border bg-surface-1 shadow-float">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit) addMut.mutate();
          }}
          className="flex items-center gap-3 border-b border-border px-4 py-3"
        >
          <Link2 className="h-4 w-4 shrink-0 text-ink-2" />
          <input
            ref={inputRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Dán link Instagram, X hoặc TikTok…"
            className="flex-1 bg-transparent font-mono text-sm text-ink placeholder:text-ink-3 focus:outline-none"
            aria-label="Đường dẫn cần tải"
          />
          {addMut.isPending && <Loader2 className="h-4 w-4 animate-spin text-ink-2" />}
          <ShortcutChip>Esc</ShortcutChip>
        </form>

        <div className="px-4 py-3 text-xs">
          {!value.trim() && (
            <div className="text-ink-3">Nền tảng sẽ được nhận diện tự động từ đường dẫn.</div>
          )}
          {value.trim() && detected?.platform && (
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2 text-ink">
                <PlatformDot platform={detected.platform} className="h-1.5 w-1.5" />
                <span>{PLATFORM_LABEL[detected.platform]}</span>
                <span className="text-ink-3">·</span>
                <span className="truncate font-mono text-ink-2">{detected.url}</span>
              </div>
              <button
                type="button"
                onClick={() => addMut.mutate()}
                disabled={!canSubmit}
                className={cn(
                  "inline-flex shrink-0 items-center gap-1.5 rounded-md bg-accent px-2.5 py-1.5 font-medium text-background",
                  "transition-colors hover:bg-accent/90 disabled:opacity-50"
                )}
              >
                <Plus className="h-3.5 w-3.5" /> Thêm vào hàng đợi <ShortcutChip className="border-transparent bg-black/10 text-background">↵</ShortcutChip>
              </button>
            </div>
          )}
          {value.trim() && detected && !detected.platform && (
            <div className="text-warning">Không nhận diện được nền tảng. Hỗ trợ instagram.com, x.com / twitter.com, tiktok.com.</div>
          )}
        </div>
      </div>
    </div>
  );
}
