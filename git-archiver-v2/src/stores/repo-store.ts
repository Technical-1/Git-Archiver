import { create } from "zustand";
import type { Repository, RepoStatus } from "@/lib/types";
import * as commands from "@/lib/commands";

export interface RepoStore {
  repos: Repository[];
  loading: boolean;
  searchQuery: string;
  statusFilter: RepoStatus | null;
  fetchRepos: () => Promise<void>;
  addRepo: (url: string) => Promise<void>;
  deleteRepo: (id: number, removeFiles: boolean) => Promise<void>;
  setSearchQuery: (q: string) => void;
  setStatusFilter: (s: RepoStatus | null) => void;
  updateRepo: (repo: Repository) => void;
}

export const useRepoStore = create<RepoStore>((set, get) => ({
  repos: [],
  loading: false,
  searchQuery: "",
  statusFilter: null,

  fetchRepos: async () => {
    set({ loading: true });
    try {
      const statusFilter = get().statusFilter;
      const repos = await commands.listRepos(
        statusFilter ?? undefined,
      );
      set({ repos, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  addRepo: async (url: string) => {
    const repo = await commands.addRepo(url);
    set((state) => ({ repos: [...state.repos, repo] }));
  },

  deleteRepo: async (id: number, removeFiles: boolean) => {
    await commands.deleteRepo(id, removeFiles);
    set((state) => ({
      repos: state.repos.filter((r) => r.id !== id),
    }));
  },

  setSearchQuery: (q: string) => {
    set({ searchQuery: q });
  },

  setStatusFilter: (s: RepoStatus | null) => {
    set({ statusFilter: s });
  },

  updateRepo: (repo: Repository) => {
    set((state) => ({
      repos: state.repos.map((r) => (r.id === repo.id ? repo : r)),
    }));
  },
}));
