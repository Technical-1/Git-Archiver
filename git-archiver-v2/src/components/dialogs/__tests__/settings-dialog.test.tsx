import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SettingsDialog } from "../settings-dialog";
import { useSettingsStore } from "@/stores/settings-store";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

const mockSaveSettings = vi.fn();

describe("SettingsDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSaveSettings.mockReset();
    useSettingsStore.setState({
      settings: {
        data_dir: "data",
        archive_format: "tar.xz",
        max_concurrent_tasks: 4,
        auto_check_interval_minutes: null,
      },
      saveSettings: mockSaveSettings,
    });
  });

  it("renders dialog when open", () => {
    render(<SettingsDialog open={true} onOpenChange={() => {}} />);
    expect(screen.getByText("Settings")).toBeInTheDocument();
    expect(
      screen.getByText("Configure Git Archiver preferences"),
    ).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(<SettingsDialog open={false} onOpenChange={() => {}} />);
    expect(screen.queryByText("Settings")).not.toBeInTheDocument();
  });

  it("shows GitHub token input", () => {
    render(<SettingsDialog open={true} onOpenChange={() => {}} />);
    expect(screen.getByLabelText("GitHub Token")).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("ghp_xxxxxxxxxxxx"),
    ).toBeInTheDocument();
  });

  it("toggles token visibility", () => {
    render(<SettingsDialog open={true} onOpenChange={() => {}} />);
    const input = screen.getByPlaceholderText("ghp_xxxxxxxxxxxx");
    expect(input).toHaveAttribute("type", "password");

    fireEvent.click(screen.getByLabelText("Show token"));
    expect(input).toHaveAttribute("type", "text");

    fireEvent.click(screen.getByLabelText("Hide token"));
    expect(input).toHaveAttribute("type", "password");
  });

  it("shows Test button for GitHub token", () => {
    render(<SettingsDialog open={true} onOpenChange={() => {}} />);
    expect(screen.getByText("Test")).toBeInTheDocument();
  });

  it("shows max concurrent operations slider", () => {
    render(<SettingsDialog open={true} onOpenChange={() => {}} />);
    expect(
      screen.getByText("Max Parallel Operations: 4"),
    ).toBeInTheDocument();
  });

  it("shows auto-update checkbox", () => {
    render(<SettingsDialog open={true} onOpenChange={() => {}} />);
    expect(screen.getByLabelText("Enable auto-update")).toBeInTheDocument();
  });

  it("shows interval input when auto-update is enabled", () => {
    render(<SettingsDialog open={true} onOpenChange={() => {}} />);

    const checkbox = screen.getByLabelText("Enable auto-update");
    expect(screen.queryByLabelText("Check every")).not.toBeInTheDocument();

    fireEvent.click(checkbox);
    expect(screen.getByLabelText("Check every")).toBeInTheDocument();
  });

  it("shows data path as read-only", () => {
    render(<SettingsDialog open={true} onOpenChange={() => {}} />);
    const dataInput = screen.getByDisplayValue("data");
    expect(dataInput).toBeDisabled();
  });

  it("calls saveSettings and closes on save", async () => {
    mockSaveSettings.mockResolvedValueOnce(undefined);
    const onOpenChange = vi.fn();

    render(<SettingsDialog open={true} onOpenChange={onOpenChange} />);
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => {
      expect(mockSaveSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          max_concurrent_tasks: 4,
          auto_check_interval_minutes: null,
        }),
        undefined,
      );
    });

    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it("calls onOpenChange(false) on cancel", () => {
    const onOpenChange = vi.fn();
    render(<SettingsDialog open={true} onOpenChange={onOpenChange} />);
    fireEvent.click(screen.getByText("Cancel"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("passes token to saveSettings when provided", async () => {
    mockSaveSettings.mockResolvedValueOnce(undefined);
    const onOpenChange = vi.fn();

    render(<SettingsDialog open={true} onOpenChange={onOpenChange} />);

    const tokenInput = screen.getByPlaceholderText("ghp_xxxxxxxxxxxx");
    fireEvent.change(tokenInput, { target: { value: "ghp_test123" } });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => {
      expect(mockSaveSettings).toHaveBeenCalledWith(
        expect.any(Object),
        "ghp_test123",
      );
    });
  });

  it("loads auto-update interval from settings", () => {
    useSettingsStore.setState({
      settings: {
        data_dir: "data",
        archive_format: "tar.xz",
        max_concurrent_tasks: 8,
        auto_check_interval_minutes: 30,
      },
      saveSettings: mockSaveSettings,
    });

    render(<SettingsDialog open={true} onOpenChange={() => {}} />);
    expect(
      screen.getByText("Max Parallel Operations: 8"),
    ).toBeInTheDocument();
    expect(
      (screen.getByLabelText("Enable auto-update") as HTMLInputElement).checked,
    ).toBe(true);
    expect(
      (screen.getByLabelText("Check every") as HTMLInputElement).value,
    ).toBe("30");
  });
});
