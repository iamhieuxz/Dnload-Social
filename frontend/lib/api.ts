import axios from "axios";

// Use a relative `/api/...` base URL so the Next.js dev server proxy
// (configured in next.config.js) handles the rewrite to the backend.
// Falling back to a full origin only happens server-side where
// `window` is undefined, so SSR doesn't depend on env vars either.
const baseURL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (typeof window !== "undefined" ? "" : "http://localhost:8000");

export const api = axios.create({
  baseURL,
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Lightweight retry for transient failures: 5xx and network errors.
// Skips 4xx (caller's fault, retrying won't help) and POST/PATCH/DELETE
// (mutations — retry could double-charge). GET is idempotent and safe
// to retry up to 2 times with a 400ms backoff.
api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const config = err?.config;
    if (!config || config.__retried || (config.method && config.method.toUpperCase() !== "GET")) {
      throw err;
    }
    const status = err?.response?.status;
    const transient = !status || status >= 500;
    if (!transient) throw err;
    config.__retried = true;
    await new Promise((r) => setTimeout(r, 400));
    return api.request(config);
  }
);

export interface OverviewStats {
  total_accounts: number;
  total_media: number;
  total_size_bytes: number;
  total_posts: number;
  total_stories: number;
  total_highlights: number;
  jobs_running: number;
  jobs_completed_24h: number;
  jobs_failed_24h: number;
}

export interface Account {
  id: number;
  username: string;
  destination_folder: string;
  first_scanned_at: string | null;
  last_scanned_at: string | null;
  total_posts: number;
  total_stories: number;
  total_highlights: number;
  total_size_bytes: number;
  is_dead: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface Media {
  id: number;
  account_id: number;
  media_type: "post" | "story" | "highlight";
  file_path: string;
  file_name: string;
  shortcode: string | null;
  instagram_date: string | null;
  file_size_bytes: number;
  downloaded_at: string;
}

export type JobType = "add_new" | "update_list" | "update_all" | "single";
export type JobStatus = "queued" | "running" | "completed" | "stopped" | "failed";

export interface Job {
  id: number;
  job_type: JobType;
  status: JobStatus;
  targets: string | null;
  include_posts: boolean;
  include_stories: boolean;
  include_highlights: boolean;
  disable_range: boolean;
  started_at: string | null;
  finished_at: string | null;
  new_files_count: number;
  total_processed: number;
  error_message: string | null;
  duration_seconds: number | null;
  created_at: string;
  updated_at: string;
}

export interface JobCreate {
  job_type: JobType;
  targets: string[];
  include_posts?: boolean;
  include_stories?: boolean;
  include_highlights?: boolean;
  disable_range?: boolean;
}

export interface Settings {
  download_folder: string;
  twitter_download_folder: string;
  tiktok_download_folder: string;
  cookie_folder: string;
  rate_limit_min_delay: number;
  rate_limit_max_delay: number;
  rate_limit_batch_size: number;
  rate_limit_batch_cooldown: number;
  rate_limit_limit_cooldown: number;
  rate_limit_max_signals: number;
  cookies_configured: boolean;
}

export interface TwitterCookieItem {
  slot: "primary" | "backup";
  file_name: string;
  file_path: string;
  size_bytes: number;
  exists_on_disk: boolean;
  uploaded_at: string | null;
  last_used_at: string | null;
}

export interface TwitterCookieListResponse {
  items: TwitterCookieItem[];
  total: number;
}

export interface TikTokCookieItem {
  slot: "primary" | "backup";
  file_name: string;
  file_path: string;
  size_bytes: number;
  exists_on_disk: boolean;
  uploaded_at: string | null;
  last_used_at: string | null;
}

export interface TikTokCookieListResponse {
  items: TikTokCookieItem[];
  total: number;
}

// ===== Gallery types (E:\gallery-dl manager) =====
export type GalleryKind = "image" | "video" | "text" | "other";

export interface GalleryNode {
  name: string;
  path: string;
  rel_path: string;
  is_dir: boolean;
  size_bytes: number;
  file_count: number;
  folder_count: number;
  mtime: number;
  ctime?: number;        // created time (Windows birth time, normalized to Unix-seconds)
  ext?: string;          // only for files, set by /browse (uppercase routes don't set it)
  kind?: GalleryKind;
  children: GalleryNode[] | null;
}

export interface GalleryFileInfo {
  name: string;
  path: string;
  rel_path: string;
  size_bytes: number;
  mtime: number;
  ctime?: number;
  mtime_iso: string;
  ctime_iso?: string;
  mime: string;
  kind: GalleryKind;
  ext: string;
}

export interface GallerySearchItem {
  name: string;
  rel_path: string;
  path: string;
  size_bytes: number;
  mtime: number;
  ctime?: number;
  kind: GalleryKind;
  ext: string;
}

export interface GalleryStats {
  root: string;
  total_files: number;
  total_folders: number;
  total_size_bytes: number;
  by_extension: Record<string, number>;
  by_top_folder: Record<string, number>;
  largest_files: GallerySearchItem[];
  newest_files: GallerySearchItem[];
}

// ===== Downloads (queue table) =====
export type DownloadPlatform = "instagram" | "twitter" | "tiktok";
export type DownloadSource = "link" | "list" | "database";
export type DownloadStatus =
  | "pending"
  | "downloading"
  | "completed"
  | "failed"
  | "skipped";

export interface DownloadItem {
  id: number;
  job_id: number | null;
  account_id: number | null;
  platform: DownloadPlatform;
  source_type: DownloadSource;
  url: string;
  shortcode: string | null;
  media_type: string | null;
  content_type: string | null;
  title: string | null;
  author: string | null;
  file_path: string | null;
  file_name: string | null;
  file_size_bytes: number;
  thumbnail_url: string | null;
  status: DownloadStatus;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface DownloadListResponse {
  items: DownloadItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface DownloadStats {
  total: number;
  by_platform: Record<string, number>;
  by_status: Record<string, number>;
  by_source: Record<string, number>;
  total_size_bytes: number;
  last_24h: number;
  last_7d: number;
}

// ===== Dashboard (all-in-one payload) =====

export interface MediaByTypeFE {
  posts: number;
  stories: number;
  highlights: number;
}

export interface PlatformCountFE {
  platform: "instagram" | "twitter" | "tiktok" | string;
  accounts: number;
  pending: number;
  in_flight: number;
  completed: number;
  failed: number;
  completed_24h: number;
  bytes_total: number;
  files_on_disk: number;
  folders_on_disk: number;
  last_download_at: string | null;
}

export interface TopAccountFE {
  id: number;
  username: string;
  platform: string;
  total_posts: number;
  total_stories: number;
  total_highlights: number;
  total_size_bytes: number;
  is_dead: boolean;
  last_scanned_at: string | null;
}

export interface DashboardStatsFE {
  total_accounts: number;
  total_media: number;
  media_by_type: MediaByTypeFE;
  total_size_bytes: number;

  disk_total_bytes: number;
  disk_used_bytes: number;
  disk_free_bytes: number;
  files_on_disk: number;
  folders_on_disk: number;

  pending_count: number;
  in_flight_count: number;
  downloads_24h: number;
  downloads_7d: number;
  last_download_at: string | null;

  jobs_running: number;
  jobs_completed_24h: number;
  jobs_failed_24h: number;
  jobs_stopped_24h: number;
  success_rate_24h: number;       // 0.0–1.0, -1 if no jobs in window

  rate_limit_events_24h: number;
  last_rate_limit_at: string | null;

  by_platform: PlatformCountFE[];
  top_accounts_by_size: TopAccountFE[];
}
