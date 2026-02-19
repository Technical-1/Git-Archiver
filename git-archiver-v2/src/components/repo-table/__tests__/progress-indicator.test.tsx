import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { ProgressIndicator } from "../progress-indicator";
import { useTaskStore } from "@/stores/task-store";
import type { TaskProgress } from "@/lib/types";

const REPO_URL = "https://github.com/test/repo";

describe("ProgressIndicator", () => {
  beforeEach(() => {
    useTaskStore.setState({ activeTasks: new Map() });
  });

  it("renders nothing when no active task exists", () => {
    const { container } = render(<ProgressIndicator repoUrl={REPO_URL} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows spinner and stage label for active task without progress", () => {
    const tasks = new Map<string, TaskProgress>();
    tasks.set(REPO_URL, {
      repo_url: REPO_URL,
      stage: "cloning",
      progress: null,
      message: null,
    });
    useTaskStore.setState({ activeTasks: tasks });

    render(<ProgressIndicator repoUrl={REPO_URL} />);
    expect(screen.getByTestId("progress-indicator")).toBeInTheDocument();
    expect(screen.getByText("Cloning")).toBeInTheDocument();
    expect(screen.queryByTestId("progress-bar")).not.toBeInTheDocument();
  });

  it("shows progress bar when progress is available", () => {
    const tasks = new Map<string, TaskProgress>();
    tasks.set(REPO_URL, {
      repo_url: REPO_URL,
      stage: "archiving",
      progress: 45,
      message: null,
    });
    useTaskStore.setState({ activeTasks: tasks });

    render(<ProgressIndicator repoUrl={REPO_URL} />);
    expect(screen.getByText("Archiving")).toBeInTheDocument();
    expect(screen.getByTestId("progress-bar")).toBeInTheDocument();
    expect(screen.getByText("45%")).toBeInTheDocument();
  });

  it("shows correct labels for each stage", () => {
    const stages: Array<{ stage: TaskProgress["stage"]; label: string }> = [
      { stage: "cloning", label: "Cloning" },
      { stage: "pulling", label: "Pulling" },
      { stage: "archiving", label: "Archiving" },
      { stage: "compressing", label: "Compressing" },
      { stage: "checking_status", label: "Checking" },
    ];

    for (const { stage, label } of stages) {
      const tasks = new Map<string, TaskProgress>();
      tasks.set(REPO_URL, {
        repo_url: REPO_URL,
        stage,
        progress: null,
        message: null,
      });
      useTaskStore.setState({ activeTasks: tasks });

      const { unmount } = render(<ProgressIndicator repoUrl={REPO_URL} />);
      expect(screen.getByText(label)).toBeInTheDocument();
      unmount();
    }
  });

  it("caps progress bar at 100%", () => {
    const tasks = new Map<string, TaskProgress>();
    tasks.set(REPO_URL, {
      repo_url: REPO_URL,
      stage: "compressing",
      progress: 150,
      message: null,
    });
    useTaskStore.setState({ activeTasks: tasks });

    render(<ProgressIndicator repoUrl={REPO_URL} />);
    const bar = screen.getByTestId("progress-bar");
    expect(bar.style.width).toBe("100%");
  });
});
