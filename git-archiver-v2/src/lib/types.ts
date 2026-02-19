// TypeScript interfaces matching Rust backend models.
// Field names use snake_case to match Tauri's serde serialization.

export type RepoStatus = "pending" | "active" | "archived" | "deleted" | "error";

export interface Repository {
  id: number | null;
  owner: string;
  name: string;
  url: string;
  status: RepoStatus;
  description: string | null;
  is_private: boolean;
  local_path: string | null;
  last_checked: string | null;
  last_archived: string | null;
  error_message: string | null;
  created_at: string;
}

export interface ArchiveView {
  id: number | null;
  repo_id: number;
  filename: string;
  file_size: number;
  file_count: number;
  is_incremental: boolean;
  created_at: string;
}

export type TaskStage =
  | "cloning"
  | "pulling"
  | "archiving"
  | "compressing"
  | "checking_status";

export interface TaskProgress {
  repo_url: string;
  stage: TaskStage;
  progress: number | null;
  message: string | null;
}

export interface AppSettings {
  data_dir: string;
  archive_format: string;
  max_concurrent_tasks: number;
  auto_check_interval_minutes: number | null;
}

export interface RateLimitInfo {
  limit: number;
  remaining: number;
  reset: number;
}

export interface BulkAddResult {
  added: number;
  skipped: number;
  errors: string[];
}

export interface ActivityEntry {
  id: string;
  timestamp: string;
  message: string;
  type: "info" | "success" | "error" | "warning";
  repo_url?: string;
}
