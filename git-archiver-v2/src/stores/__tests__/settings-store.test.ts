import { describe, it, expect, vi, beforeEach } from "vitest";
import { useSettingsStore } from "../settings-store";
import type { AppSettings } from "@/lib/types";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

const mockSettings: AppSettings = {
  data_dir: "/custom/data",
  archive_format: "tar.gz",
  max_concurrent_tasks: 8,
  auto_check_interval_minutes: 60,
};

describe("settings-store", () => {
  beforeEach(() => {
    useSettingsStore.setState({
      settings: {
        data_dir: "data",
        archive_format: "tar.xz",
        max_concurrent_tasks: 4,
        auto_check_interval_minutes: null,
      },
      loading: false,
    });
    vi.clearAllMocks();
  });

  it("has correct initial state", () => {
    const state = useSettingsStore.getState();
    expect(state.settings.data_dir).toBe("data");
    expect(state.settings.archive_format).toBe("tar.xz");
    expect(state.settings.max_concurrent_tasks).toBe(4);
    expect(state.settings.auto_check_interval_minutes).toBeNull();
    expect(state.loading).toBe(false);
  });

  it("fetchSettings loads settings from backend", async () => {
    const { invoke } = await import("@tauri-apps/api/core");
    vi.mocked(invoke).mockResolvedValueOnce(mockSettings);

    await useSettingsStore.getState().fetchSettings();

    const state = useSettingsStore.getState();
    expect(state.settings).toEqual(mockSettings);
    expect(state.loading).toBe(false);
    expect(invoke).toHaveBeenCalledWith("get_settings");
  });

  it("fetchSettings sets loading to false on error", async () => {
    const { invoke } = await import("@tauri-apps/api/core");
    vi.mocked(invoke).mockRejectedValueOnce(new Error("Failed"));

    await useSettingsStore.getState().fetchSettings();

    expect(useSettingsStore.getState().loading).toBe(false);
  });

  it("saveSettings sends settings to backend and updates state", async () => {
    const { invoke } = await import("@tauri-apps/api/core");
    vi.mocked(invoke).mockResolvedValueOnce(undefined);

    await useSettingsStore.getState().saveSettings(mockSettings);

    const state = useSettingsStore.getState();
    expect(state.settings).toEqual(mockSettings);
    expect(invoke).toHaveBeenCalledWith("save_settings", {
      settings: mockSettings,
      token: undefined,
    });
  });

  it("saveSettings passes token when provided", async () => {
    const { invoke } = await import("@tauri-apps/api/core");
    vi.mocked(invoke).mockResolvedValueOnce(undefined);

    await useSettingsStore.getState().saveSettings(mockSettings, "ghp_abc123");

    expect(invoke).toHaveBeenCalledWith("save_settings", {
      settings: mockSettings,
      token: "ghp_abc123",
    });
  });
});
