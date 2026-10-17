"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Settings, type TwitterCookieItem, type TwitterCookieListResponse, type TikTokCookieItem, type TikTokCookieListResponse } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/PageHeader";
import { PlatformDot } from "@/components/PlatformDot";
import { ShortcutChip } from "@/components/ShortcutChip";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Upload, Trash2, FolderOpen, Cookie, Gauge, Database,
  Instagram, Twitter, Music, ChevronDown, CheckCircle2, XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";

type PlatformCookieItem = TwitterCookieItem | TikTokCookieItem;

// Section ids for the accordion (plan §6.6 — sticky accordion)
const SECTION = {
  storage: "storage",
  ig:      "instagram",
  x:       "twitter",
  tiktok:  "tiktok",
  rate:    "rate",
} as const;
type SectionId = typeof SECTION[keyof typeof SECTION];

const ALL_SECTIONS: SectionId[] = [SECTION.storage, SECTION.ig, SECTION.x, SECTION.tiktok, SECTION.rate];

const PLATFORM_META: Record<string, { label: string; icon: typeof Instagram; dot: string }> = {
  instagram: { label: "Instagram", icon: Instagram, dot: "instagram" },
  twitter:   { label: "Twitter / X", icon: Twitter, dot: "twitter" },
  tiktok:    { label: "TikTok",   icon: Music,  dot: "tiktok" },
};

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data, refetch } = useQuery<Settings>({
    queryKey: ["settings"],
    queryFn: async () => (await api.get("/api/settings")).data,
  });

  // Accordion — all open by default; remember last choice in localStorage.
  const [openSet, setOpenSet] = useState<Set<SectionId>>(
    () => new Set<SectionId>(ALL_SECTIONS)
  );
  useEffect(() => {
    try {
      const raw = localStorage.getItem("settings:sections");
      if (raw) {
        const arr = JSON.parse(raw) as SectionId[];
        if (Array.isArray(arr) && arr.every((s) => ALL_SECTIONS.includes(s))) {
          setOpenSet(new Set(arr));
        }
      }
    } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    try { localStorage.setItem("settings:sections", JSON.stringify([...openSet])); } catch { /* ignore */ }
  }, [openSet]);

  const toggle = (id: SectionId) =>
    setOpenSet((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // Cookie-slot refs
  const c1Ref = useRef<HTMLInputElement | null>(null);
  const c2Ref = useRef<HTMLInputElement | null>(null);
  const tc1Ref = useRef<HTMLInputElement | null>(null);
  const tc2Ref = useRef<HTMLInputElement | null>(null);
  const ttc1Ref = useRef<HTMLInputElement | null>(null);
  const ttc2Ref = useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState<1 | 2 | "primary" | "backup" | "tt-primary" | "tt-backup" | null>(null);

  // Shared upload helper — the three cookie namespaces (IG, X, TikTok)
  // differ only in endpoint, success message, and which query key to
  // invalidate. One function takes all three as parameters.
  async function uploadCookie(
    slot: NonNullable<typeof uploading>,
    file: File,
    opts: { endpoint: string; successMessage: string; invalidates?: string[] }
  ) {
    // Shortcut: pre-check the 10MB server cap so the user gets an
    // immediate toast instead of waiting for the request to fail.
    // The server still enforces it; this is purely UX.
    if (file.size > 10 * 1024 * 1024) {
      toast.error(`Cookie file too large (${(file.size / 1024 / 1024).toFixed(1)}MB, max 10MB)`);
      return;
    }
    setUploading(slot);
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api.post(opts.endpoint, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(opts.successMessage);
      if (opts.invalidates) {
        for (const key of opts.invalidates) {
          if (key === "settings") refetch();
          else qc.invalidateQueries({ queryKey: [key] });
        }
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Upload failed");
    } finally {
      setUploading(null);
    }
  }

  const upload = (slot: 1 | 2, file: File) =>
    uploadCookie(slot, file, {
      endpoint: `/api/cookies/upload/${slot}`,
      successMessage: `Cookie slot ${slot} uploaded`,
      invalidates: ["settings"],
    });

  const uploadTwitter = (slot: "primary" | "backup", file: File) =>
    uploadCookie(slot, file, {
      endpoint: `/api/cookies/twitter/upload/${slot}`,
      successMessage: `Twitter cookie (${slot}) uploaded`,
      invalidates: ["twitter-cookies", "settings"],
    });

  const uploadTikTok = (slot: "primary" | "backup", file: File) => {
    const key: "tt-primary" | "tt-backup" = slot === "primary" ? "tt-primary" : "tt-backup";
    return uploadCookie(key, file, {
      endpoint: `/api/cookies/tiktok/upload/${slot}`,
      successMessage: `TikTok cookie (${slot}) uploaded`,
      invalidates: ["tiktok-cookies", "settings"],
    });
  };

  const removeCookie = useMutation({
    mutationFn: async (slot: 1 | 2) => (await api.delete(`/api/cookies/${slot}`)).data,
    onSuccess: () => {
      toast.success("Cookie removed");
      refetch();
    },
  });
  const removeTwitterCookie = useMutation({
    mutationFn: async (slot: "primary" | "backup") =>
      (await api.delete(`/api/cookies/twitter/${slot}`)).data,
    onSuccess: () => {
      toast.success("Twitter cookie removed");
      qc.invalidateQueries({ queryKey: ["twitter-cookies"] });
    },
  });
  const removeTikTokCookie = useMutation({
    mutationFn: async (slot: "primary" | "backup") =>
      (await api.delete(`/api/cookies/tiktok/${slot}`)).data,
    onSuccess: () => {
      toast.success("TikTok cookie removed");
      qc.invalidateQueries({ queryKey: ["tiktok-cookies"] });
    },
  });

  const { data: twCookies } = useQuery<TwitterCookieListResponse>({
    queryKey: ["twitter-cookies"],
    queryFn: async () => (await api.get("/api/cookies/twitter/list")).data,
  });
  const { data: ttCookies } = useQuery<TikTokCookieListResponse>({
    queryKey: ["tiktok-cookies"],
    queryFn: async () => (await api.get("/api/cookies/tiktok/list")).data,
  });

  return (
    <div className="space-y-4 max-w-4xl">
      <PageHeader
        title="Settings"
        description="Configure storage, cookies and rate limits"
      />

      {/* ---- Storage section (per-platform folder rows) ---- */}
      <AccordionSection
        id={SECTION.storage}
        title="Storage"
        subtitle="Các thư mục gốc cho từng nền tảng"
        icon={Database}
        open={openSet.has(SECTION.storage)}
        onToggle={() => toggle(SECTION.storage)}
      >
        <FolderRow
          platform="instagram"
          label="Instagram folder"
          path={data?.download_folder}
          icon={Instagram}
        />
        <FolderRow
          platform="twitter"
          label="Twitter / X folder"
          path={data?.twitter_download_folder}
          icon={Twitter}
        />
        <FolderRow
          platform="tiktok"
          label="TikTok folder"
          path={data?.tiktok_download_folder}
          icon={Music}
        />
        <FolderRow platform="cookie" label="Cookie folder" path={data?.cookie_folder} icon={Cookie} />
        <p className="text-[11px] text-muted-foreground pt-2">
          Cấu hình từ backend <code className="font-mono">.env</code>. Restart server để thay đổi có hiệu lực.
        </p>
      </AccordionSection>

      {/* ---- Instagram cookies ---- */}
      <AccordionSection
        id={SECTION.ig}
        title="Instagram cookies"
        subtitle="2 slot: 1 chính + 1 backup"
        icon={Instagram}
        open={openSet.has(SECTION.ig)}
        onToggle={() => toggle(SECTION.ig)}
      >
        <CookieSlot
          slot={1}
          label="Cookie 1"
          sublabel="primary — bắt buộc"
          uploading={uploading === 1}
          onFile={(f) => upload(1, f)}
          onRemove={() => removeCookie.mutate(1)}
          inputRef={c1Ref}
        />
        <CookieSlot
          slot={2}
          label="Cookie 2"
          sublabel="backup — tuỳ chọn"
          uploading={uploading === 2}
          onFile={(f) => upload(2, f)}
          onRemove={() => removeCookie.mutate(2)}
          inputRef={c2Ref}
        />
      </AccordionSection>

      {/* ---- X / Twitter cookies ---- */}
      <AccordionSection
        id={SECTION.x}
        title="X / Twitter cookies"
        subtitle="Lưu cả DB và on-disk dưới secrets/cookies/twitter/"
        icon={Twitter}
        open={openSet.has(SECTION.x)}
        onToggle={() => toggle(SECTION.x)}
      >
        <p className="text-[11px] text-muted-foreground -mt-1 mb-1">
          Dùng cho yt-dlp khi tải tweet / video / ended-Space.
        </p>
        <TwitterCookieSlot
          slot="primary"
          cookie={twCookies?.items.find((i) => i.slot === "primary")}
          uploading={uploading === "primary"}
          onFile={(f) => uploadTwitter("primary", f)}
          onRemove={() => removeTwitterCookie.mutate("primary")}
          inputRef={tc1Ref}
        />
        <TwitterCookieSlot
          slot="backup"
          cookie={twCookies?.items.find((i) => i.slot === "backup")}
          uploading={uploading === "backup"}
          onFile={(f) => uploadTwitter("backup", f)}
          onRemove={() => removeTwitterCookie.mutate("backup")}
          inputRef={tc2Ref}
        />
      </AccordionSection>

      {/* ---- TikTok cookies ---- */}
      <AccordionSection
        id={SECTION.tiktok}
        title="TikTok cookies"
        subtitle="Quan trọng — không có sessionid thì gallery-dl bị rate-limit 5-10 phút/request"
        icon={Music}
        open={openSet.has(SECTION.tiktok)}
        onToggle={() => toggle(SECTION.tiktok)}
      >
        <p className="text-[11px] text-muted-foreground -mt-1 mb-1 leading-relaxed">
          Lưu cả DB và on-disk dưới <code className="font-mono">secrets/cookies/tiktok/</code>.
          Không có <code className="font-mono">sessionid</code> → rate-limit anonymous → 6 accounts mất 1 giờ.
          Upload cookie để cắt xuống vài giây/item.
        </p>
        <p className="text-[10px] text-muted-foreground/80 -mt-1 mb-2 leading-relaxed">
          Export tip: đăng nhập tiktok.com trong Chrome, dùng extension "Get cookies.txt LOCALLY" hoặc
          {" "}<code className="font-mono">yt-dlp --cookies-from-browser chrome --cookies tt_cookie1.txt https://www.tiktok.com</code>.
        </p>
        <TwitterCookieSlot
          slot="primary"
          cookie={ttCookies?.items.find((i) => i.slot === "primary")}
          uploading={uploading === "tt-primary"}
          onFile={(f) => uploadTikTok("primary", f)}
          onRemove={() => removeTikTokCookie.mutate("primary")}
          inputRef={ttc1Ref}
        />
        <TwitterCookieSlot
          slot="backup"
          cookie={ttCookies?.items.find((i) => i.slot === "backup")}
          uploading={uploading === "tt-backup"}
          onFile={(f) => uploadTikTok("backup", f)}
          onRemove={() => removeTikTokCookie.mutate("backup")}
          inputRef={ttc2Ref}
        />
      </AccordionSection>

      {/* ---- Rate limit ---- */}
      <AccordionSection
        id={SECTION.rate}
        title="Rate limit policy"
        subtitle="Đọc-only từ backend .env"
        icon={Gauge}
        open={openSet.has(SECTION.rate)}
        onToggle={() => toggle(SECTION.rate)}
      >
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm">
          <Row label="Min delay (s)" value={data?.rate_limit_min_delay} />
          <Row label="Max delay (s)" value={data?.rate_limit_max_delay} />
          <Row label="Batch size" value={data?.rate_limit_batch_size} />
          <Row label="Batch cooldown (s)" value={data?.rate_limit_batch_cooldown} />
          <Row label="Limit cooldown (s)" value={data?.rate_limit_limit_cooldown} />
          <Row label="Max signals" value={data?.rate_limit_max_signals} />
        </div>
        <p className="text-[11px] text-muted-foreground pt-3">
          Sửa <code className="font-mono">.env</code> rồi restart server để thay đổi.
          Phím tắt: <ShortcutChip>Esc</ShortcutChip> đóng modal, <ShortcutChip>?</ShortcutChip> mở shortcut help.
        </p>
      </AccordionSection>
    </div>
  );
}

// =====================================================================
// Accordion section (plan §6.6 — sticky accordion, lucide chevron)
// =====================================================================

function AccordionSection({
  id, title, subtitle, icon: Icon, open, onToggle, children,
}: {
  id: SectionId;
  title: string;
  subtitle?: string;
  icon: typeof Database;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={`section-${id}`}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-2"
      >
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-muted">
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{title}</div>
          {subtitle && <div className="text-[11px] text-muted-foreground">{subtitle}</div>}
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180"
          )}
        />
      </button>
      {open && (
        <div id={`section-${id}`} className="space-y-3 border-t border-border px-4 py-3">
          {children}
        </div>
      )}
    </Card>
  );
}

// =====================================================================
// Folder row — single platform path with platform dot + "open in Explorer"
// (just a copyable path; the real "open in Explorer" needs a backend
// endpoint which doesn't exist yet, so we show the path in mono for now).
// =====================================================================

function FolderRow({
  platform, label, path, icon: Icon,
}: {
  platform: "instagram" | "twitter" | "tiktok" | "cookie";
  label: string;
  path: string | undefined;
  icon: typeof FolderOpen;
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-background px-3 py-2.5">
      <div className="flex h-7 w-7 items-center justify-center rounded-md bg-muted">
        <Icon className="h-3.5 w-3.5" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium flex items-center gap-1.5">
          {platform !== "cookie" && <PlatformDot platform={platform} />}
          {label}
        </div>
        <div
          className="truncate font-mono text-[11px] text-muted-foreground"
          title={path}
        >
          {path ?? "—"}
        </div>
      </div>
      {path && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            navigator.clipboard?.writeText(path).then(
              () => toast.success("Đã copy path"),
              () => toast.error("Không copy được")
            );
          }}
          className="gap-1.5 text-muted-foreground"
          title="Copy path"
        >
          <FolderOpen className="h-3.5 w-3.5" /> Copy
        </Button>
      )}
    </div>
  );
}

function Row({
  label, value, icon: Icon,
}: {
  label: string;
  value: string | number | undefined;
  icon?: typeof FolderOpen;
}) {
  return (
    <div className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-2 gap-2">
      <span className="text-muted-foreground flex items-center gap-1.5 text-[11px]">
        {Icon && <Icon className="h-3 w-3" />}
        {label}
      </span>
      <span className="font-mono text-sm">{value ?? "—"}</span>
    </div>
  );
}

function CookieSlot({
  slot, label, sublabel, uploading, onFile, onRemove, inputRef,
}: {
  slot: 1 | 2;
  label: string;
  sublabel: string;
  uploading: boolean;
  onFile: (f: File) => void;
  onRemove: () => void;
  inputRef: React.MutableRefObject<HTMLInputElement | null>;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2.5 hover:border-foreground/30 transition-colors">
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-muted font-mono text-xs font-bold">
          {slot}
        </div>
        <div>
          <div className="text-sm font-medium">{label}</div>
          <div className="text-[11px] text-muted-foreground font-mono">
            {sublabel} · cookie{slot}.txt
          </div>
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        <input
          ref={inputRef}
          type="file"
          accept=".txt"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onFile(f);
            e.target.value = "";
          }}
        />
        <Button variant="outline" size="sm" disabled={uploading} onClick={() => inputRef.current?.click()}>
          <Upload className="h-3.5 w-3.5" /> {uploading ? "Uploading…" : "Upload"}
        </Button>
        <Button variant="ghost" size="icon" onClick={onRemove} title="Xoá cookie">
          <Trash2 className="h-3.5 w-3.5 text-destructive" />
        </Button>
      </div>
    </div>
  );
}

function TwitterCookieSlot({
  slot, cookie, uploading, onFile, onRemove, inputRef,
}: {
  slot: "primary" | "backup";
  cookie?: PlatformCookieItem;
  uploading: boolean;
  onFile: (f: File) => void;
  onRemove: () => void;
  inputRef: React.MutableRefObject<HTMLInputElement | null>;
}) {
  const present = !!cookie?.exists_on_disk;
  const label = slot === "primary" ? "Primary" : "Backup";
  const defaultFile = (cookie as TwitterCookieItem | undefined)?.file_name ?? "tt_cookie1.txt";
  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2.5 hover:border-foreground/30 transition-colors">
      <div className="flex items-center gap-3">
        <div className={cn(
          "flex h-8 w-8 items-center justify-center rounded-md font-mono text-sm font-bold border",
          present ? "status-success" : "border-border bg-muted text-muted-foreground"
        )}>
          {present ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
        </div>
        <div>
          <div className="text-sm font-medium flex items-center gap-1.5">
            {label}
            <span className={cn(
              "text-[10px] px-1.5 py-0.5 rounded-full font-mono uppercase tracking-wider border",
              present ? "status-success" : "status-muted"
            )}>
              {present ? "set" : "empty"}
            </span>
          </div>
          <div className="text-[11px] text-muted-foreground font-mono">
            {cookie?.file_name ?? defaultFile}{cookie ? ` · ${(cookie.size_bytes/1024).toFixed(1)}KB` : ""}
            {cookie?.uploaded_at ? ` · ${new Date(cookie.uploaded_at).toLocaleString()}` : ""}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        <input
          ref={inputRef}
          type="file"
          accept=".txt"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onFile(f);
            e.target.value = "";
          }}
        />
        <Button variant="outline" size="sm" disabled={uploading} onClick={() => inputRef.current?.click()}>
          <Upload className="h-3.5 w-3.5" /> {uploading ? "Uploading…" : "Upload"}
        </Button>
        <Button variant="ghost" size="icon" onClick={onRemove} disabled={!present}>
          <Trash2 className="h-3.5 w-3.5 text-destructive" />
        </Button>
      </div>
    </div>
  );
}
