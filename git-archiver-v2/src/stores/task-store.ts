import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { TaskProgress, ActivityEntry } from "@/lib/types";

const MAX_LOG_ENTRIES = 100;

export interface TaskStore {
  activeTasks: Map<string, TaskProgress>;
  activityLog: ActivityEntry[];
  addProgress: (progress: TaskProgress) => void;
  removeTask: (repoUrl: string) => void;
  addLogEntry: (entry: ActivityEntry) => void;
}

export const useTaskStore = create<TaskStore>()(
  persist(
    (set) => ({
      activeTasks: new Map(),
      activityLog: [],

      addProgress: (progress: TaskProgress) => {
        set((state) => {
          const newTasks = new Map(state.activeTasks);
          // Backend sends progress as 0.0-1.0 ratio; convert to 0-100 for display
          const normalized = {
            ...progress,
            progress:
              progress.progress !== null && progress.progress !== undefined
                ? progress.progress * 100
                : null,
          };
          newTasks.set(progress.repo_url, normalized);
          return { activeTasks: newTasks };
        });
      },

      removeTask: (repoUrl: string) => {
        set((state) => {
          const newTasks = new Map(state.activeTasks);
          newTasks.delete(repoUrl);
          return { activeTasks: newTasks };
        });
      },

      addLogEntry: (entry: ActivityEntry) => {
        set((state) => ({
          activityLog: [entry, ...state.activityLog].slice(0, MAX_LOG_ENTRIES),
        }));
      },
    }),
    {
      name: "git-archiver-activity-log",
      partialize: (state) => ({ activityLog: state.activityLog }),
    },
  ),
);
