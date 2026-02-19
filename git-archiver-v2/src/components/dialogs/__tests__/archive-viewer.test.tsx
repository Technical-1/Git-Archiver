import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ArchiveViewer } from "../archive-viewer";
import type { Repository, ArchiveView } from "@/lib/types";

const mockListArchives = vi.fn();
const mockExtractArchive = vi.fn();
const mockDeleteArchive = vi.fn();

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

vi.mock("@/lib/commands", () => ({
  listArchives: (...args: unknown[]) => mockListArchives(...args),
  extractArchive: (...args: unknown[]) => mockExtractArchive(...args),
  deleteArchive: (...args: unknown[]) => mockDeleteArchive(...args),
}));

const repo: Repository = {
  id: 1,
  owner: "octocat",
  name: "hello-world",
  url: "https://github.com/octocat/hello-world",
  status: "active",
  description: null,
  is_private: false,
  local_path: null,
  last_checked: null,
  last_archived: null,
  error_message: null,
  created_at: "2026-01-01T00:00:00Z",
};

const sampleArchives: ArchiveView[] = [
  {
    id: 10,
    repo_id: 1,
    filename: "hello-world-2026-01-15.tar.xz",
    file_size: 1048576, // 1 MB
    file_count: 42,
    is_incremental: false,
    created_at: "2026-01-15T10:30:00Z",
  },
  {
    id: 11,
    repo_id: 1,
    filename: "hello-world-2026-01-20.tar.xz",
    file_size: 524288, // 512 KB
    file_count: 5,
    is_incremental: true,
    created_at: "2026-01-20T14:00:00Z",
  },
];

describe("ArchiveViewer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when closed", () => {
    render(
      <ArchiveViewer repo={repo} open={false} onOpenChange={() => {}} />,
    );
    expect(screen.queryByText(/Archives:/)).not.toBeInTheDocument();
  });

  it("shows loading state when open", () => {
    mockListArchives.mockReturnValue(new Promise(() => {})); // never resolves
    render(
      <ArchiveViewer repo={repo} open={true} onOpenChange={() => {}} />,
    );
    expect(screen.getByText("Loading archives...")).toBeInTheDocument();
  });

  it("shows empty state when no archives exist", async () => {
    mockListArchives.mockResolvedValueOnce([]);
    render(
      <ArchiveViewer repo={repo} open={true} onOpenChange={() => {}} />,
    );
    await waitFor(() => {
      expect(screen.getByText("No archives found.")).toBeInTheDocument();
    });
  });

  it("shows archives in table", async () => {
    mockListArchives.mockResolvedValueOnce(sampleArchives);
    render(
      <ArchiveViewer repo={repo} open={true} onOpenChange={() => {}} />,
    );

    await waitFor(() => {
      expect(screen.getByText("2 archives available")).toBeInTheDocument();
    });

    // Check columns
    expect(screen.getByText("1.0 MB")).toBeInTheDocument();
    expect(screen.getByText("512.0 KB")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("Full")).toBeInTheDocument();
    expect(screen.getByText("Incremental")).toBeInTheDocument();
  });

  it("shows dialog title with repo name", async () => {
    mockListArchives.mockResolvedValueOnce([]);
    render(
      <ArchiveViewer repo={repo} open={true} onOpenChange={() => {}} />,
    );
    expect(
      screen.getByText("Archives: octocat/hello-world"),
    ).toBeInTheDocument();
  });

  it("shows delete confirmation on delete button click", async () => {
    mockListArchives.mockResolvedValueOnce(sampleArchives);
    render(
      <ArchiveViewer repo={repo} open={true} onOpenChange={() => {}} />,
    );

    await waitFor(() => {
      expect(screen.getByText("1.0 MB")).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByLabelText("Delete archive");
    fireEvent.click(deleteButtons[0]);

    expect(screen.getByText("Confirm")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("deletes archive on confirm", async () => {
    mockListArchives.mockResolvedValueOnce(sampleArchives);
    mockDeleteArchive.mockResolvedValueOnce(undefined);

    render(
      <ArchiveViewer repo={repo} open={true} onOpenChange={() => {}} />,
    );

    await waitFor(() => {
      expect(screen.getByText("1.0 MB")).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByLabelText("Delete archive");
    fireEvent.click(deleteButtons[0]);
    fireEvent.click(screen.getByText("Confirm"));

    await waitFor(() => {
      expect(mockDeleteArchive).toHaveBeenCalledWith(10);
    });
  });

  it("cancels delete confirmation", async () => {
    mockListArchives.mockResolvedValueOnce(sampleArchives);

    render(
      <ArchiveViewer repo={repo} open={true} onOpenChange={() => {}} />,
    );

    await waitFor(() => {
      expect(screen.getByText("1.0 MB")).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByLabelText("Delete archive");
    fireEvent.click(deleteButtons[0]);
    expect(screen.getByText("Confirm")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Cancel"));
    expect(screen.queryByText("Confirm")).not.toBeInTheDocument();
  });
});
