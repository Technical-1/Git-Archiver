import { describe, it, expect, vi, beforeEach } from "vitest";
import { useRepoStore } from "../repo-store";
import type { Repository } from "@/lib/types";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

const mockRepo: Repository = {
  id: 1,
  owner: "octocat",
  name: "hello-world",
  url: "https://github.com/octocat/hello-world",
  status: "active",
  description: "A test repo",
  is_private: false,
  local_path: "/data/octocat/hello-world.git",
  last_checked: "2025-06-15T12:00:00Z",
  last_archived: null,
  error_message: null,
  created_at: "2025-06-01T00:00:00Z",
};

const mockRepo2: Repository = {
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
};

describe("repo-store", () => {
  beforeEach(() => {
    // Reset the store state between tests
    useRepoStore.setState({
      repos: [],
      loading: false,
      searchQuery: "",
      statusFilter: null,
    });
    vi.clearAllMocks();
  });

  it("has correct initial state", () => {
    const state = useRepoStore.getState();
    expect(state.repos).toEqual([]);
    expect(state.loading).toBe(false);
    expect(state.searchQuery).toBe("");
    expect(state.statusFilter).toBeNull();
  });

  it("fetchRepos loads repos from backend", async () => {
    const { invoke } = await import("@tauri-apps/api/core");
    vi.mocked(invoke).mockResolvedValueOnce([mockRepo, mockRepo2]);

    await useRepoStore.getState().fetchRepos();

    const state = useRepoStore.getState();
    expect(state.repos).toHaveLength(2);
    expect(state.repos[0].name).toBe("hello-world");
    expect(state.loading).toBe(false);
    expect(invoke).toHaveBeenCalledWith("list_repos", {
      statusFilter: undefined,
    });
  });

  it("fetchRepos passes status filter", async () => {
    const { invoke } = await import("@tauri-apps/api/core");
    vi.mocked(invoke).mockResolvedValueOnce([mockRepo]);

    useRepoStore.setState({ statusFilter: "active" });
    await useRepoStore.getState().fetchRepos();

    expect(invoke).toHaveBeenCalledWith("list_repos", {
      statusFilter: "active",
    });
  });

  it("fetchRepos sets loading to false on error", async () => {
    const { invoke } = await import("@tauri-apps/api/core");
    vi.mocked(invoke).mockRejectedValueOnce(new Error("Network error"));

    await useRepoStore.getState().fetchRepos();

    expect(useRepoStore.getState().loading).toBe(false);
  });

  it("addRepo adds a repo to the list", async () => {
    const { invoke } = await import("@tauri-apps/api/core");
    vi.mocked(invoke).mockResolvedValueOnce(mockRepo);

    await useRepoStore.getState().addRepo("https://github.com/octocat/hello-world");

    const state = useRepoStore.getState();
    expect(state.repos).toHaveLength(1);
    expect(state.repos[0]).toEqual(mockRepo);
  });

  it("deleteRepo removes a repo from the list", async () => {
    const { invoke } = await import("@tauri-apps/api/core");
    vi.mocked(invoke).mockResolvedValueOnce(undefined);

    useRepoStore.setState({ repos: [mockRepo, mockRepo2] });
    await useRepoStore.getState().deleteRepo(1, false);

    const state = useRepoStore.getState();
    expect(state.repos).toHaveLength(1);
    expect(state.repos[0].id).toBe(2);
  });

  it("setSearchQuery updates the query", () => {
    useRepoStore.getState().setSearchQuery("test");
    expect(useRepoStore.getState().searchQuery).toBe("test");
  });

  it("setStatusFilter updates the filter", () => {
    useRepoStore.getState().setStatusFilter("error");
    expect(useRepoStore.getState().statusFilter).toBe("error");
  });

  it("setStatusFilter can clear the filter", () => {
    useRepoStore.setState({ statusFilter: "active" });
    useRepoStore.getState().setStatusFilter(null);
    expect(useRepoStore.getState().statusFilter).toBeNull();
  });

  it("updateRepo replaces a repo in the list by id", () => {
    useRepoStore.setState({ repos: [mockRepo, mockRepo2] });

    const updated = { ...mockRepo, status: "archived" as const };
    useRepoStore.getState().updateRepo(updated);

    const state = useRepoStore.getState();
    expect(state.repos[0].status).toBe("archived");
    expect(state.repos[1].id).toBe(2);
  });

  it("updateRepo does nothing if id not found", () => {
    useRepoStore.setState({ repos: [mockRepo] });

    const unknown = { ...mockRepo2, id: 999 };
    useRepoStore.getState().updateRepo(unknown);

    expect(useRepoStore.getState().repos).toHaveLength(1);
    expect(useRepoStore.getState().repos[0].id).toBe(1);
  });
});
