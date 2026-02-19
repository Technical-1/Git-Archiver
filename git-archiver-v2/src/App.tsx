import { useEffect } from "react";
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

  // Subscribe to Tauri backend events
  useEffect(() => {
    const unlistenProgress = listen<TaskProgress>(
      "task-progress",
      (event) => {
        taskStore.addProgress(event.payload);
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
