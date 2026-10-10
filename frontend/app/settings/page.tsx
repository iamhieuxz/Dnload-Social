"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Settings, type TwitterCookieItem, type TwitterCookieListResponse } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Upload, Trash2, FolderOpen, Cookie, Gauge, Database, Twitter, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export default function SettingsPage() {
  const { data, refetch } = useQuery<Settings>({
    queryKey: ["settings"],
    queryFn: async () => (await api.get("/api/settings")).data,
  });

  const c1Ref = useRef<HTMLInputElement | null>(null);
  const c2Ref = useRef<HTMLInputElement | null>(null);
  const tc1Ref = useRef<HTMLInputElement | null>(null);
  const tc2Ref = useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState<1 | 2 | "primary" | "backup" | null>(null);

  async function upload(slot: 1 | 2, file: File) {
    setUploading(slot);
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api.post(`/api/cookies/upload/${slot}`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Cookie slot ${slot} uploaded`);
      refetch();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Upload failed");
    } finally {
      setUploading(null);
    }
  }

  async function uploadTwitter(slot: "primary" | "backup", file: File) {
    setUploading(slot);
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api.post(`/api/cookies/twitter/upload/${slot}`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Twitter cookie (${slot}) uploaded`);
      refetch();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Upload failed");
    } finally {
      setUploading(null);
    }
  }

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
      qcTw.invalidateQueries({ queryKey: ["twitter-cookies"] });
    },
  });

  // Live status from DB so the user can see which X slots are actually set
  const qcTw = useQueryClient();
  const { data: twCookies, refetch: refetchTw } = useQuery<TwitterCookieListResponse>({
    queryKey: ["twitter-cookies"],
    queryFn: async () => (await api.get("/api/cookies/twitter/list")).data,
  });

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">
          <span className="gradient-text">Settings</span>
        </h2>
        <p className="text-muted-foreground mt-1">Configure storage, cookies and rate limits</p>
      </div>

      <Card variant="glass">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-accent/20">
              <Database className="h-4 w-4 text-accent" />
            </div>
            Storage
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <Row label="Download folder" value={data?.download_folder} icon={FolderOpen} />
          <Row label="Cookie folder" value={data?.cookie_folder} icon={Cookie} />
          <p className="text-xs text-muted-foreground pt-2">
            These come from the backend's <code className="text-primary">.env</code>. Restart the backend to change.
          </p>
        </CardContent>
      </Card>

      <Card variant="glass">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/20">
              <Cookie className="h-4 w-4 text-primary" />
            </div>
            Instagram cookies
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <CookieSlot
            slot={1}
            label="Cookie 1"
            sublabel="primary — required"
            uploading={uploading === 1}
            onFile={(f) => upload(1, f)}
            onRemove={() => removeCookie.mutate(1)}
            inputRef={c1Ref}
          />
          <CookieSlot
            slot={2}
            label="Cookie 2"
            sublabel="backup — optional"
            uploading={uploading === 2}
            onFile={(f) => upload(2, f)}
            onRemove={() => removeCookie.mutate(2)}
            inputRef={c2Ref}
          />
        </CardContent>
      </Card>

      <Card variant="glass">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[#1da1f2]/20">
              <Twitter className="h-4 w-4 text-[#1da1f2]" />
            </div>
            X / Twitter cookies
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-muted-foreground -mt-1 mb-2">
            Stored in the database (<code className="text-primary">twitter_cookies</code>) + on disk
            under <code>secrets/cookies/twitter/</code>. Used by yt-dlp for tweet / video /
            ended-Space downloads.
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
        </CardContent>
      </Card>

      <Card variant="glass">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-warning/20">
              <Gauge className="h-4 w-4 text-warning" />
            </div>
            Rate limit policy
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
          <Row label="Min delay (s)" value={data?.rate_limit_min_delay} />
          <Row label="Max delay (s)" value={data?.rate_limit_max_delay} />
          <Row label="Batch size" value={data?.rate_limit_batch_size} />
          <Row label="Batch cooldown (s)" value={data?.rate_limit_batch_cooldown} />
          <Row label="Limit cooldown (s)" value={data?.rate_limit_limit_cooldown} />
          <Row label="Max signals" value={data?.rate_limit_max_signals} />
        </CardContent>
      </Card>
    </div>
  );
}

function Row({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string | number | undefined;
  icon?: typeof FolderOpen;
}) {
  return (
    <div className="flex items-center justify-between border-b border-white/5 py-2.5 gap-2">
      <span className="text-muted-foreground flex items-center gap-2 text-xs">
        {Icon && <Icon className="h-3.5 w-3.5" />}
        {label}
      </span>
      <span className="font-mono text-sm truncate max-w-[60%]">{value ?? "—"}</span>
    </div>
  );
}

function CookieSlot({
  slot,
  label,
  sublabel,
  uploading,
  onFile,
  onRemove,
  inputRef,
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
    <div className="group flex items-center justify-between rounded-lg border border-white/5 bg-background/30 p-3 hover:border-white/10 transition-colors">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 font-mono text-sm font-bold text-primary">
          {slot}
        </div>
        <div>
          <div className="text-sm font-medium">{label}</div>
          <div className="text-xs text-muted-foreground">
            {sublabel} · cookie{slot}.txt
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2">
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
          <Upload className="h-4 w-4" /> {uploading ? "Uploading..." : "Upload"}
        </Button>
        <Button variant="ghost" size="icon" onClick={onRemove}>
          <Trash2 className="h-4 w-4 text-destructive" />
        </Button>
      </div>
    </div>
  );
}

function TwitterCookieSlot({
  slot,
  cookie,
  uploading,
  onFile,
  onRemove,
  inputRef,
}: {
  slot: "primary" | "backup";
  cookie?: TwitterCookieItem;
  uploading: boolean;
  onFile: (f: File) => void;
  onRemove: () => void;
  inputRef: React.MutableRefObject<HTMLInputElement | null>;
}) {
  const present = !!cookie?.exists_on_disk;
  const label = slot === "primary" ? "Primary" : "Backup";
  return (
    <div className="group flex items-center justify-between rounded-lg border border-white/5 bg-background/30 p-3 hover:border-white/10 transition-colors">
      <div className="flex items-center gap-3">
        <div className={cn(
          "flex h-9 w-9 items-center justify-center rounded-md font-mono text-sm font-bold",
          present
            ? "bg-success/20 text-success"
            : "bg-white/5 text-muted-foreground"
        )}>
          {present ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
        </div>
        <div>
          <div className="text-sm font-medium flex items-center gap-2">
            {label}
            <span className={cn(
              "text-[10px] px-1.5 py-0.5 rounded-full font-mono uppercase tracking-wider",
              present ? "bg-success/15 text-success" : "bg-muted text-muted-foreground"
            )}>
              {present ? "set" : "empty"}
            </span>
          </div>
          <div className="text-xs text-muted-foreground">
            {cookie?.file_name ?? "tw_cookie1.txt"}{cookie ? ` · ${(cookie.size_bytes/1024).toFixed(1)}KB` : ""}
            {cookie?.uploaded_at ? ` · ${new Date(cookie.uploaded_at).toLocaleString()}` : ""}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2">
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
          <Upload className="h-4 w-4" /> {uploading ? "Uploading..." : "Upload"}
        </Button>
        <Button variant="ghost" size="icon" onClick={onRemove} disabled={!present}>
          <Trash2 className="h-4 w-4 text-destructive" />
        </Button>
      </div>
    </div>
  );
}
