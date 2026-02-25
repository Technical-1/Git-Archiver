import { useEffect, useRef } from "react";
import { listen } from "@tauri-apps/api/event";
import { ThemeProvider } from "next-themes";
import { AppHeader } from "@/components/app-header";
import { AddRepoBar } from "@/components/add-repo-bar";
import { DataTable } from "@/components/repo-table/data-table";
import { ActivityLog } from "@/components/activity-log";
import { StatusBar } from "@/components/status-bar";
import { Toaster } from "@/components/ui/toaster";
import { useRepoStore } from "@/stores/repo-store";
import { useTaskStore } from "@/stores/task-store";
import { useSettingsStore } from "@/stores/settings-store";
import type { TaskProgress, Repository } from "@/lib/types";

interface TaskErrorPayload {
  repo_url: string;
  message: string;
}

/** Extract "owner/repo" from a GitHub URL for display in log messages. */
function shortName(repoUrl: string): string {
  try {
    const parts = new URL(repoUrl).pathname.split("/").filter(Boolean);
    if (parts.length >= 2) return `${parts[0]}/${parts[1]}`;
  } catch {
    // fall through
  }
  return repoUrl;
}

function App() {
  const repoStore = useRepoStore();
  const taskStore = useTaskStore();
  const settingsStore = useSettingsStore();

  // Initial data fetch on mount
  useEffect(() => {
    repoStore.fetchRepos();
    settingsStore.fetchSettings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Track which repo_urls we've already logged as "started"
  const seenTasksRef = useRef<Set<string>>(new Set());

  // Subscribe to Tauri backend events
  useEffect(() => {
    const unlistenProgress = listen<TaskProgress>(
      "task-progress",
      (event) => {
        const { repo_url, stage } = event.payload;
        taskStore.addProgress(event.payload);

        // Log "Started ..." on first appearance of this repo_url
        if (repo_url && !seenTasksRef.current.has(repo_url)) {
          seenTasksRef.current.add(repo_url);
          const action = stage === "cloning" ? "cloning" : "updating";
          taskStore.addLogEntry({
            id: `${Date.now()}-start-${repo_url}`,
            timestamp: new Date().toISOString(),
            message: `Started ${action} ${shortName(repo_url)}`,
            type: "info",
            repo_url,
          });
        }
      },
    );

    const unlistenComplete = listen<string>(
      "task-complete",
      (event) => {
        const repoUrl = event.payload;

        // Determine action from the last known stage
        const lastTask = taskStore.activeTasks.get(repoUrl);
        const wasClone = lastTask?.stage === "cloning" || lastTask?.stage === "archiving";
        const action = wasClone && !seenTasksRef.current.has(`updated:${repoUrl}`)
          ? "Cloned" : "Updated";

        taskStore.addLogEntry({
          id: `${Date.now()}-complete-${repoUrl}`,
          timestamp: new Date().toISOString(),
          message: `${action} ${shortName(repoUrl)} successfully`,
          type: "success",
          repo_url: repoUrl,
        });

        // Clean up tracking
        seenTasksRef.current.delete(repoUrl);

        // Brief delay so the user sees the "complete" state before clearing
        setTimeout(() => {
          taskStore.removeTask(repoUrl);
          // Refresh repo list to pick up status/timestamp changes
          repoStore.fetchRepos();
        }, 1500);
      },
    );

    const unlistenError = listen<TaskErrorPayload>(
      "task-error",
      (event) => {
        const { repo_url, message } = event.payload;
        taskStore.addLogEntry({
          id: `${Date.now()}-error-${repo_url}`,
          timestamp: new Date().toISOString(),
          message: `Failed: ${shortName(repo_url)} — ${message}`,
          type: "error",
          repo_url,
        });

        // Clean up tracking
        seenTasksRef.current.delete(repo_url);
      },
    );

    const unlistenRepoUpdated = listen<Repository>(
      "repo-updated",
      (event) => {
        repoStore.updateRepo(event.payload);
      },
    );

    return () => {
      unlistenProgress.then((fn) => fn());
      unlistenComplete.then((fn) => fn());
      unlistenError.then((fn) => fn());
      unlistenRepoUpdated.then((fn) => fn());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <div className="flex flex-col h-screen bg-background text-foreground">
        <AppHeader />
        <main className="flex-1 overflow-auto p-4 space-y-4">
          <AddRepoBar />
          <DataTable />
        </main>
        <ActivityLog />
        <StatusBar />
      </div>
      <Toaster />
    </ThemeProvider>
  );
}
export default App;
