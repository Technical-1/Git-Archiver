import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { normalizeRepoUrl, isValidGithubUrl, formatRelativeTime } from "../utils";

describe("normalizeRepoUrl", () => {
  it("lowercases the URL", () => {
    expect(normalizeRepoUrl("https://GitHub.com/Owner/Repo")).toBe(
      "https://github.com/owner/repo",
    );
  });

  it("strips trailing slashes", () => {
    expect(normalizeRepoUrl("https://github.com/owner/repo/")).toBe(
      "https://github.com/owner/repo",
    );
    expect(normalizeRepoUrl("https://github.com/owner/repo///")).toBe(
      "https://github.com/owner/repo",
    );
  });

  it("strips .git suffix", () => {
    expect(normalizeRepoUrl("https://github.com/owner/repo.git")).toBe(
      "https://github.com/owner/repo",
    );
  });

  it("upgrades http to https", () => {
    expect(normalizeRepoUrl("http://github.com/owner/repo")).toBe(
      "https://github.com/owner/repo",
    );
  });

  it("handles combined normalizations", () => {
    expect(normalizeRepoUrl("http://GitHub.com/Owner/Repo.git/")).toBe(
      "https://github.com/owner/repo",
    );
  });

  it("trims whitespace", () => {
    expect(normalizeRepoUrl("  https://github.com/owner/repo  ")).toBe(
      "https://github.com/owner/repo",
    );
  });
});

describe("isValidGithubUrl", () => {
  it("accepts valid https URLs", () => {
    expect(isValidGithubUrl("https://github.com/owner/repo")).toBe(true);
  });

  it("accepts valid http URLs", () => {
    expect(isValidGithubUrl("http://github.com/owner/repo")).toBe(true);
  });

  it("accepts URLs without protocol", () => {
    expect(isValidGithubUrl("github.com/owner/repo")).toBe(true);
  });

  it("accepts URLs with .git suffix", () => {
    expect(isValidGithubUrl("https://github.com/owner/repo.git")).toBe(true);
  });

  it("accepts URLs with trailing slash", () => {
    expect(isValidGithubUrl("https://github.com/owner/repo/")).toBe(true);
  });

  it("accepts URLs with www prefix", () => {
    expect(isValidGithubUrl("https://www.github.com/owner/repo")).toBe(true);
  });

  it("accepts owner/repo with hyphens, dots, and underscores", () => {
    expect(isValidGithubUrl("https://github.com/my-org/my_repo.js")).toBe(true);
  });

  it("rejects empty strings", () => {
    expect(isValidGithubUrl("")).toBe(false);
    expect(isValidGithubUrl("   ")).toBe(false);
  });

  it("rejects non-github URLs", () => {
    expect(isValidGithubUrl("https://gitlab.com/owner/repo")).toBe(false);
  });

  it("rejects URLs without owner/repo", () => {
    expect(isValidGithubUrl("https://github.com/owner")).toBe(false);
    expect(isValidGithubUrl("https://github.com/")).toBe(false);
  });

  it("rejects URLs with extra path segments", () => {
    expect(isValidGithubUrl("https://github.com/owner/repo/tree/main")).toBe(
      false,
    );
  });

  it("rejects random strings", () => {
    expect(isValidGithubUrl("not a url")).toBe(false);
  });
});

describe("formatRelativeTime", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2025-06-15T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns "just now" for times less than 60 seconds ago', () => {
    expect(formatRelativeTime("2025-06-15T11:59:30Z")).toBe("just now");
  });

  it('returns "1 minute ago" for exactly 1 minute ago', () => {
    expect(formatRelativeTime("2025-06-15T11:59:00Z")).toBe("1 minute ago");
  });

  it("returns minutes ago", () => {
    expect(formatRelativeTime("2025-06-15T11:45:00Z")).toBe("15 minutes ago");
  });

  it('returns "1 hour ago"', () => {
    expect(formatRelativeTime("2025-06-15T11:00:00Z")).toBe("1 hour ago");
  });

  it("returns hours ago", () => {
    expect(formatRelativeTime("2025-06-15T09:00:00Z")).toBe("3 hours ago");
  });

  it('returns "1 day ago"', () => {
    expect(formatRelativeTime("2025-06-14T12:00:00Z")).toBe("1 day ago");
  });

  it("returns days ago", () => {
    expect(formatRelativeTime("2025-06-12T12:00:00Z")).toBe("3 days ago");
  });

  it('returns "1 week ago"', () => {
    expect(formatRelativeTime("2025-06-08T12:00:00Z")).toBe("1 week ago");
  });

  it("returns weeks ago", () => {
    expect(formatRelativeTime("2025-06-01T12:00:00Z")).toBe("2 weeks ago");
  });

  it('returns "1 month ago"', () => {
    expect(formatRelativeTime("2025-05-15T12:00:00Z")).toBe("1 month ago");
  });

  it("returns months ago", () => {
    expect(formatRelativeTime("2025-03-15T12:00:00Z")).toBe("3 months ago");
  });

  it('returns "1 year ago"', () => {
    expect(formatRelativeTime("2024-06-15T12:00:00Z")).toBe("1 year ago");
  });

  it("returns years ago", () => {
    expect(formatRelativeTime("2023-06-15T12:00:00Z")).toBe("2 years ago");
  });

  it('returns "just now" for future dates', () => {
    expect(formatRelativeTime("2025-06-16T12:00:00Z")).toBe("just now");
  });
});
