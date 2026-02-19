import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { StatusBar } from "../status-bar";
import { useRepoStore } from "@/stores/repo-store";
import { useTaskStore } from "@/stores/task-store";
import type { Repository, TaskProgress } from "@/lib/types";

const makeRepo = (id: number, name: string): Repository => ({
  id,
  owner: "test",
  name,
  url: `https://github.com/test/${name}`,
  status: "active",
  description: null,
  is_private: false,
  local_path: null,
  last_checked: null,
  last_archived: null,
  error_message: null,
  created_at: "2026-01-01T00:00:00Z",
});

describe("StatusBar", () => {
  beforeEach(() => {
    useRepoStore.setState({ repos: [] });
    useTaskStore.setState({ activeTasks: new Map() });
  });

  it("renders status bar with zero repos", () => {
    render(<StatusBar />);
    expect(screen.getByTestId("status-bar")).toBeInTheDocument();
    expect(screen.getByText("0 repositories")).toBeInTheDocument();
  });

  it("shows correct repo count with singular form", () => {
    useRepoStore.setState({ repos: [makeRepo(1, "repo-a")] });
    render(<StatusBar />);
    expect(screen.getByText("1 repository")).toBeInTheDocument();
  });

  it("shows correct repo count with plural form", () => {
    useRepoStore.setState({
      repos: [makeRepo(1, "repo-a"), makeRepo(2, "repo-b")],
    });
    render(<StatusBar />);
    expect(screen.getByText("2 repositories")).toBeInTheDocument();
  });

  it("does not show active tasks when none exist", () => {
    render(<StatusBar />);
    expect(screen.queryByTestId("active-tasks")).not.toBeInTheDocument();
  });

  it("shows active task count when tasks are running", () => {
    const tasks = new Map<string, TaskProgress>();
    tasks.set("https://github.com/test/repo-a", {
      repo_url: "https://github.com/test/repo-a",
      stage: "cloning",
      progress: null,
      message: null,
    });
    useTaskStore.setState({ activeTasks: tasks });

    render(<StatusBar />);
    expect(screen.getByTestId("active-tasks")).toBeInTheDocument();
    expect(screen.getByText("1 active task")).toBeInTheDocument();
  });

  it("shows plural form for multiple active tasks", () => {
    const tasks = new Map<string, TaskProgress>();
    tasks.set("https://github.com/test/repo-a", {
      repo_url: "https://github.com/test/repo-a",
      stage: "cloning",
      progress: null,
      message: null,
    });
    tasks.set("https://github.com/test/repo-b", {
      repo_url: "https://github.com/test/repo-b",
      stage: "pulling",
      progress: null,
      message: null,
    });
    useTaskStore.setState({ activeTasks: tasks });

    render(<StatusBar />);
    expect(screen.getByText("2 active tasks")).toBeInTheDocument();
  });

  it("shows version text", () => {
    render(<StatusBar />);
    expect(screen.getByText("Git Archiver v2")).toBeInTheDocument();
  });
});
