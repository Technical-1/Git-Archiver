import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Normalize a GitHub repository URL:
 * - Lowercase the host and path
 * - Strip trailing slashes
 * - Strip .git suffix
 * - Upgrade http to https
 * - Ensure https://github.com/owner/repo format
 */
export function normalizeRepoUrl(url: string): string {
  let normalized = url.trim().toLowerCase();

  // Upgrade http to https
  normalized = normalized.replace(/^http:\/\//, "https://");

  // Strip trailing slashes
  normalized = normalized.replace(/\/+$/, "");

  // Strip .git suffix
  normalized = normalized.replace(/\.git$/, "");

  return normalized;
}

/**
 * Validate that a string is a valid GitHub repository URL.
 * Accepts: https://github.com/owner/repo, http://github.com/owner/repo,
 * github.com/owner/repo, and variants with .git suffix or trailing slashes.
 */
export function isValidGithubUrl(url: string): boolean {
  const trimmed = url.trim();
  if (!trimmed) return false;

  // Match github.com/owner/repo with optional protocol, .git suffix, and trailing slash
  const pattern =
    /^(https?:\/\/)?(www\.)?github\.com\/[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+(\/)?(\.git)?\/?$/;
  return pattern.test(trimmed);
}

/**
 * Format an ISO date string as a human-readable relative time.
 * Examples: "just now", "2 minutes ago", "3 hours ago", "5 days ago"
 */
export function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();

  if (diffMs < 0) return "just now";

  const seconds = Math.floor(diffMs / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  const weeks = Math.floor(days / 7);
  const months = Math.floor(days / 30);
  const years = Math.floor(days / 365);

  if (seconds < 60) return "just now";
  if (minutes === 1) return "1 minute ago";
  if (minutes < 60) return `${minutes} minutes ago`;
  if (hours === 1) return "1 hour ago";
  if (hours < 24) return `${hours} hours ago`;
  if (days === 1) return "1 day ago";
  if (days < 7) return `${days} days ago`;
  if (weeks === 1) return "1 week ago";
  if (weeks < 4) return `${weeks} weeks ago`;
  if (months === 1) return "1 month ago";
  if (months < 12) return `${months} months ago`;
  if (years === 1) return "1 year ago";
  return `${years} years ago`;
}

/**
 * Format a file size in bytes to a human-readable string.
 * Examples: "1.2 KB", "3.5 MB", "2.1 GB"
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 0) return "0 B";
  if (bytes === 0) return "0 B";

  const units = ["B", "KB", "MB", "GB", "TB"];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const index = Math.min(i, units.length - 1);

  if (index === 0) return `${bytes} B`;
  return `${(bytes / Math.pow(k, index)).toFixed(1)} ${units[index]}`;
}
