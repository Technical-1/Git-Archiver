import { create } from "zustand";
import type { AppSettings } from "@/lib/types";
import * as commands from "@/lib/commands";

export interface SettingsStore {
  settings: AppSettings;
  loading: boolean;
  fetchSettings: () => Promise<void>;
  saveSettings: (settings: AppSettings, token?: string) => Promise<void>;
}

const defaultSettings: AppSettings = {
  data_dir: "data",
  archive_format: "tar.xz",
  max_concurrent_tasks: 4,
  auto_check_interval_minutes: null,
};

export const useSettingsStore = create<SettingsStore>((set) => ({
  settings: defaultSettings,
  loading: false,

  fetchSettings: async () => {
    set({ loading: true });
    try {
      const settings = await commands.getSettings();
      set({ settings, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  saveSettings: async (settings: AppSettings, token?: string) => {
    await commands.saveSettings(settings, token);
    set({ settings });
  },
}));
