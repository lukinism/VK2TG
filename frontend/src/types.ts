export type TransferStatus = "queued" | "success" | "error" | "skipped" | "partial";

export interface SourceSettings {
  include_text: boolean;
  include_photos: boolean;
  include_videos: boolean;
  include_audio: boolean;
  include_documents: boolean;
  include_links: boolean;
  include_signature: boolean;
  include_original_date: boolean;
  include_original_link: boolean;
  include_reposts: boolean;
  include_subscriber_posts: boolean;
  poll_count: number;
}

export interface SourceSchedule {
  timezone_name: string;
  interval_seconds: number;
  priority: number;
  active_weekdays: number[];
  window_start?: string | null;
  window_end?: string | null;
  pause_until?: string | null;
  base_backoff_seconds: number;
  max_backoff_seconds: number;
}

export interface SourceRuntimeState {
  next_run_at?: string | null;
  last_started_at?: string | null;
  last_finished_at?: string | null;
  consecutive_failures: number;
  last_error_at?: string | null;
  last_error_message?: string | null;
  last_outcome?: string | null;
  scheduler_status: string;
  scheduler_note?: string | null;
}

export interface VKSource {
  id: string;
  name: string;
  screen_name: string;
  group_id: number | null;
  is_active: boolean;
  telegram_target: string;
  settings: SourceSettings;
  schedule: SourceSchedule;
  runtime: SourceRuntimeState;
  last_checked_at: string | null;
  last_detected_post_id: number | null;
  last_transferred_post_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface TransferAttachment {
  type: string;
  url?: string | null;
  title?: string | null;
  artist?: string | null;
  local_path?: string | null;
  sent: boolean;
  skipped: boolean;
  error?: string | null;
}

export interface TransferRecord {
  id: string;
  created_at: string;
  updated_at: string;
  source_id: string;
  source_name: string;
  vk_post_id: number;
  vk_post_url: string;
  telegram_target: string;
  telegram_message_ids: number[];
  telegram_message_url?: string | null;
  status: TransferStatus;
  attempts: number;
  error?: string | null;
  post_text: string;
  post_created_at?: string | null;
  attachments: TransferAttachment[];
  technical_logs: string[];
}

export interface LogEntry {
  id: string;
  timestamp: string;
  level: string;
  event: string;
  message: string;
  source_id?: string | null;
  transfer_id?: string | null;
}

export interface CacheFileInfo {
  name: string;
  relative_path: string;
  size_bytes: number;
  modified_at: string;
}

export interface CacheOverview {
  files: CacheFileInfo[];
  total_files: number;
  total_size_bytes: number;
}

export interface DashboardStats {
  vk_groups: number;
  telegram_targets: number;
  successful_transfers: number;
  failed_transfers: number;
  queued_transfers: number;
  last_check_at?: string | null;
  worker_status: string;
  stats_today: number;
  stats_7d: number;
  stats_30d: number;
}

export interface SessionInfo {
  authenticated: boolean;
  username?: string | null;
  csrf_token?: string | null;
}

export interface SettingsView {
  poll_interval_seconds: number;
  retry_limit: number;
  admin_username: string;
  session_secret: string;
  ffmpeg_binary: string;
  vk_token_masked: string;
  telegram_bot_token_masked: string;
  telegram_proxy_url_masked: string;
  has_vk_token: boolean;
  has_telegram_bot_token: boolean;
  has_telegram_proxy_url: boolean;
  vk_token_valid?: boolean | null;
  vk_token_validation_error?: string | null;
  vk_token_last_validated_at?: string | null;
  telegram_bot_token_valid?: boolean | null;
  telegram_bot_token_validation_error?: string | null;
  telegram_bot_token_last_validated_at?: string | null;
}

export interface SettingsUpdate {
  poll_interval_seconds: number;
  retry_limit: number;
  admin_username: string;
  session_secret: string;
  ffmpeg_binary: string;
  vk_token: string;
  telegram_bot_token: string;
  telegram_proxy_url: string;
  clear_vk_token: boolean;
  clear_telegram_token: boolean;
  clear_telegram_proxy: boolean;
}
