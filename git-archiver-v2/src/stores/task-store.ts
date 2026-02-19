import { create } from "zustand";
import type { TaskProgress, ActivityEntry } from "@/lib/types";

const MAX_LOG_ENTRIES = 100;

export interface TaskStore {
  activeTasks: Map<string, TaskProgress>;
  activityLog: ActivityEntry[];
  addProgress: (progress: TaskProgress) => void;
  removeTask: (repoUrl: string) => void;
  addLogEntry: (entry: ActivityEntry) => void;
}

export const useTaskStore = create<TaskStore>((set) => ({
  activeTasks: new Map(),
  activityLog: [],

  addProgress: (progress: TaskProgress) => {
    set((state) => {
      const newTasks = new Map(state.activeTasks);
      newTasks.set(progress.repo_url, progress);
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
}));
