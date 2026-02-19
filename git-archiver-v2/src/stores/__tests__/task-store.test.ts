import { describe, it, expect, beforeEach } from "vitest";
import { useTaskStore } from "../task-store";
import type { TaskProgress, ActivityEntry } from "@/lib/types";

describe("task-store", () => {
  beforeEach(() => {
    useTaskStore.setState({
      activeTasks: new Map(),
      activityLog: [],
    });
  });

  it("has correct initial state", () => {
    const state = useTaskStore.getState();
    expect(state.activeTasks.size).toBe(0);
    expect(state.activityLog).toEqual([]);
  });

  it("addProgress adds a task", () => {
    const progress: TaskProgress = {
      repo_url: "https://github.com/octocat/hello-world",
      stage: "cloning",
      progress: 0.5,
      message: "Cloning...",
    };

    useTaskStore.getState().addProgress(progress);

    const state = useTaskStore.getState();
    expect(state.activeTasks.size).toBe(1);
    expect(
      state.activeTasks.get("https://github.com/octocat/hello-world"),
    ).toEqual(progress);
  });

  it("addProgress updates an existing task", () => {
    const url = "https://github.com/octocat/hello-world";
    const progress1: TaskProgress = {
      repo_url: url,
      stage: "cloning",
      progress: 0.5,
      message: "Cloning...",
    };
    const progress2: TaskProgress = {
      repo_url: url,
      stage: "archiving",
      progress: 0.8,
      message: "Archiving...",
    };

    useTaskStore.getState().addProgress(progress1);
    useTaskStore.getState().addProgress(progress2);

    const state = useTaskStore.getState();
    expect(state.activeTasks.size).toBe(1);
    expect(state.activeTasks.get(url)?.stage).toBe("archiving");
  });

  it("removeTask removes a task by URL", () => {
    const url = "https://github.com/octocat/hello-world";
    const progress: TaskProgress = {
      repo_url: url,
      stage: "cloning",
      progress: null,
      message: null,
    };

    useTaskStore.getState().addProgress(progress);
    expect(useTaskStore.getState().activeTasks.size).toBe(1);

    useTaskStore.getState().removeTask(url);
    expect(useTaskStore.getState().activeTasks.size).toBe(0);
  });

  it("removeTask does nothing for unknown URL", () => {
    const progress: TaskProgress = {
      repo_url: "https://github.com/octocat/hello-world",
      stage: "cloning",
      progress: null,
      message: null,
    };

    useTaskStore.getState().addProgress(progress);
    useTaskStore.getState().removeTask("https://github.com/unknown/repo");

    expect(useTaskStore.getState().activeTasks.size).toBe(1);
  });

  it("addLogEntry adds an entry to the front", () => {
    const entry1: ActivityEntry = {
      id: "1",
      timestamp: "2025-06-15T12:00:00Z",
      message: "First entry",
      type: "info",
    };
    const entry2: ActivityEntry = {
      id: "2",
      timestamp: "2025-06-15T12:01:00Z",
      message: "Second entry",
      type: "success",
    };

    useTaskStore.getState().addLogEntry(entry1);
    useTaskStore.getState().addLogEntry(entry2);

    const state = useTaskStore.getState();
    expect(state.activityLog).toHaveLength(2);
    expect(state.activityLog[0].id).toBe("2");
    expect(state.activityLog[1].id).toBe("1");
  });

  it("addLogEntry caps the log at 100 entries", () => {
    for (let i = 0; i < 105; i++) {
      useTaskStore.getState().addLogEntry({
        id: String(i),
        timestamp: new Date().toISOString(),
        message: `Entry ${i}`,
        type: "info",
      });
    }

    expect(useTaskStore.getState().activityLog).toHaveLength(100);
    // Most recent should be entry 104 (last added)
    expect(useTaskStore.getState().activityLog[0].id).toBe("104");
  });
});
