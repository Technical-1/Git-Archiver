import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DataTable } from "../data-table";
import { useRepoStore } from "@/stores/repo-store";
import type { Repository } from "@/lib/types";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

const mockRepos: Repository[] = [
  {
    id: 1,
    owner: "octocat",
    name: "hello-world",
    url: "https://github.com/octocat/hello-world",
    status: "active",
    description: "A test repository",
    is_private: false,
    local_path: "/data/octocat/hello-world.git",
    last_checked: "2025-06-15T12:00:00Z",
    last_archived: null,
    error_message: null,
    created_at: "2025-06-01T00:00:00Z",
  },
  {
    id: 2,
    owner: "octocat",
    name: "spoon-knife",
    url: "https://github.com/octocat/spoon-knife",
    status: "pending",
    description: null,
    is_private: false,
    local_path: null,
    last_checked: null,
    last_archived: null,
    error_message: null,
    created_at: "2025-06-02T00:00:00Z",
  },
];

describe("DataTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useRepoStore.setState({
      repos: mockRepos,
      loading: false,
      searchQuery: "",
      statusFilter: null,
      fetchRepos: vi.fn(),
    });
  });

  it("renders repository names", () => {
    render(<DataTable />);
    expect(screen.getByText("hello-world")).toBeInTheDocument();
    expect(screen.getByText("spoon-knife")).toBeInTheDocument();
  });

  it("renders owner names", () => {
    render(<DataTable />);
    const ownerElements = screen.getAllByText("octocat/");
    expect(ownerElements.length).toBeGreaterThanOrEqual(2);
  });

  it("renders status badges", () => {
    render(<DataTable />);
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("renders column headers", () => {
    render(<DataTable />);
    expect(screen.getByText("Repository")).toBeInTheDocument();
    expect(screen.getByText("Description")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("Last Updated")).toBeInTheDocument();
  });

  it("shows repo count", () => {
    render(<DataTable />);
    expect(screen.getByText("2 repositories")).toBeInTheDocument();
  });

  it("shows empty state when no repos", () => {
    useRepoStore.setState({ repos: [] });
    render(<DataTable />);
    expect(screen.getByText("No repositories found.")).toBeInTheDocument();
  });

  it("shows loading state", () => {
    useRepoStore.setState({ loading: true, repos: [] });
    render(<DataTable />);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders description text", () => {
    render(<DataTable />);
    expect(screen.getByText("A test repository")).toBeInTheDocument();
  });

  it('renders "--" for missing description', () => {
    render(<DataTable />);
    expect(screen.getByText("--")).toBeInTheDocument();
  });

  it('shows "Never" for repos without last_checked', () => {
    render(<DataTable />);
    expect(screen.getByText("Never")).toBeInTheDocument();
  });

  it("calls fetchRepos on mount", () => {
    const fetchRepos = vi.fn();
    useRepoStore.setState({ fetchRepos });
    render(<DataTable />);
    expect(fetchRepos).toHaveBeenCalled();
  });

  it("filters repos by search query", () => {
    useRepoStore.setState({ searchQuery: "hello" });
    render(<DataTable />);
    expect(screen.getByText("hello-world")).toBeInTheDocument();
    expect(screen.queryByText("spoon-knife")).not.toBeInTheDocument();
  });
});
