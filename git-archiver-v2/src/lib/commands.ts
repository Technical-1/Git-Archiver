import { invoke } from "@tauri-apps/api/core";
import type {
  Repository,
  ArchiveView,
  AppSettings,
  RateLimitInfo,
  BulkAddResult,
} from "./types";

export async function addRepo(url: string): Promise<Repository> {
  return invoke("add_repo", { url });
}

export async function listRepos(
  statusFilter?: string,
): Promise<Repository[]> {
  return invoke("list_repos", { statusFilter });
}

export async function deleteRepo(
  id: number,
  removeFiles: boolean,
): Promise<void> {
  return invoke("delete_repo", { id, removeFiles });
}

export async function importFromFile(path: string): Promise<BulkAddResult> {
  return invoke("import_from_file", { path });
}

export async function cloneRepo(id: number): Promise<void> {
  return invoke("clone_repo", { id });
}

export async function updateRepo(id: number): Promise<void> {
  return invoke("update_repo", { id });
}

export async function updateAll(includeArchived: boolean): Promise<void> {
  return invoke("update_all", { includeArchived });
}

export async function stopAllTasks(): Promise<void> {
  return invoke("stop_all_tasks");
}

export async function listArchives(repoId: number): Promise<ArchiveView[]> {
  return invoke("list_archives", { repoId });
}

export async function extractArchive(
  archiveId: number,
  destDir: string,
): Promise<void> {
  return invoke("extract_archive", { archiveId, destDir });
}

export async function deleteArchive(archiveId: number): Promise<void> {
  return invoke("delete_archive", { archiveId });
}

export async function getSettings(): Promise<AppSettings> {
  return invoke("get_settings");
}

export async function saveSettings(
  settings: AppSettings,
  token?: string,
): Promise<void> {
  return invoke("save_settings", { settings, token });
}

export async function checkRateLimit(): Promise<RateLimitInfo> {
  return invoke("check_rate_limit");
}
